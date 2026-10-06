#!/usr/bin/env python3
"""Build the Economics Society's documented SQLite macro-data snapshot.

The script uses public World Bank, IMF, and India OEA sources. It stores annual
WDI series and quarterly series only. Monthly IMF/OEA inputs are aggregated to
quarterly values and are not stored. Missing observations are not filled.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import io
import json
import math
import os
import posixpath
import shutil
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from html.parser import HTMLParser
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any


WB_API = "https://api.worldbank.org/v2"
IMF_API = "https://api.imf.org/external/sdmx/2.1"
USER_AGENT = "PondicherryEconomicsSociety-MacroResearchDB/0.1"
AS_OF = dt.date.today().isoformat()
START_YEAR = 2000

WB_SERIES: dict[str, dict[str, str]] = {
    "NY.GDP.MKTP.CD": {"slug": "gdp_nominal_current_usd_annual", "name": "GDP (current US$)", "unit": "current US dollars", "description": "Annual nominal GDP at current US dollars; exchange-rate movements affect cross-country comparisons."},
    "NY.GDP.MKTP.CN": {"slug": "gdp_nominal_current_lcu_annual", "name": "GDP (current LCU)", "unit": "current local currency units", "description": "Annual nominal GDP in local currency, useful for within-country nominal growth."},
    "NY.GDP.MKTP.KD": {"slug": "gdp_real_constant_2015_usd_annual", "name": "GDP (constant 2015 US$)", "unit": "constant 2015 US dollars", "description": "Annual real GDP at constant 2015 US dollars."},
    "NY.GDP.MKTP.KN": {"slug": "gdp_real_constant_lcu_annual", "name": "GDP (constant LCU)", "unit": "constant local currency units (source base year varies)", "description": "Annual real GDP in constant local currency; base year is source-country specific."},
    "NY.GDP.PCAP.CD": {"slug": "gdp_per_capita_nominal_usd_annual", "name": "GDP per capita (current US$)", "unit": "current US dollars per person", "description": "Annual nominal GDP per capita at current US dollars."},
    "NY.GDP.PCAP.CN": {"slug": "gdp_per_capita_nominal_lcu_annual", "name": "GDP per capita (current LCU)", "unit": "current local currency units per person", "description": "Annual nominal GDP per capita in local currency."},
    "NY.GDP.PCAP.KD": {"slug": "gdp_per_capita_real_2015_usd_annual", "name": "GDP per capita (constant 2015 US$)", "unit": "constant 2015 US dollars per person", "description": "Annual real GDP per capita at constant 2015 US dollars."},
    "NY.GDP.PCAP.KN": {"slug": "gdp_per_capita_real_lcu_annual", "name": "GDP per capita (constant LCU)", "unit": "constant local currency units per person (source base year varies)", "description": "Annual real GDP per capita in constant local currency."},
    "NY.GDP.MKTP.KD.ZG": {"slug": "gdp_real_growth_yoy_pct_annual", "name": "GDP growth (annual %)", "unit": "percent per year", "description": "World Bank reported annual real GDP growth."},
    "NY.GDP.PCAP.KD.ZG": {"slug": "gdp_per_capita_real_growth_yoy_pct_annual", "name": "GDP per capita growth (annual %)", "unit": "percent per year", "description": "World Bank reported annual real GDP per-capita growth."},
    "NY.GNP.PCAP.PP.CD": {"slug": "gni_per_capita_ppp_current_intl_dollar_annual", "name": "GNI per capita, PPP (current international $)", "unit": "current international dollars per person", "description": "Gross national income per capita converted at purchasing power parity."},
    "SP.DYN.LE00.IN": {"slug": "life_expectancy_years_annual", "name": "Life expectancy at birth, total (years)", "unit": "years", "description": "Annual life expectancy at birth, total population."},
    "SL.UEM.TOTL.ZS": {"slug": "unemployment_rate_ilo_modeled_pct_annual", "name": "Unemployment, total (% of total labor force) (modeled ILO estimate)", "unit": "percent of labor force", "description": "ILO-modeled annual unemployment estimate; retain modeled status and source notes."},
    "SI.POV.DDAY": {"slug": "poverty_headcount_at_3usd_2021_ppp_pct_annual", "name": "Poverty headcount ratio at $3.00 a day (2021 PPP) (% of population)", "unit": "percent of population", "description": "World Bank international poverty measure at $3.00/day in 2021 PPP; observations follow survey availability and revisions."},
    "FP.CPI.TOTL": {"slug": "cpi_index_annual_wdi", "name": "Consumer price index (2010 = 100)", "unit": "index points (2010=100)", "description": "World Bank annual CPI index; not comparable across country index bases."},
    "FP.CPI.TOTL.ZG": {"slug": "inflation_consumer_prices_yoy_pct_annual_wdi", "name": "Inflation, consumer prices (annual %)", "unit": "percent per year", "description": "World Bank reported annual CPI inflation."},
    "SP.POP.TOTL": {"slug": "population_total_annual", "name": "Population, total", "unit": "people", "description": "World Bank annual population estimate; used to estimate quarterly GDP per capita."},
}

DERIVED_INDICATORS = [
    ("gdp_nominal_growth_yoy_pct_annual_lcu", "Nominal GDP growth, year over year (annual)", "percent per year", "Annual percent change calculated from nominal GDP in current local currency."),
    ("gdp_per_capita_nominal_growth_yoy_pct_annual_lcu", "Nominal GDP per-capita growth, year over year (annual)", "percent per year", "Annual percent change calculated from nominal GDP per capita in current local currency."),
    ("gdp_nominal_lcu_quarterly_sa", "Nominal GDP, quarterly, seasonally adjusted", "domestic currency at current prices (as reported)", "IMF QNEA GDP at current prices, domestic currency, seasonally adjusted."),
    ("gdp_nominal_lcu_quarterly_nsa", "Nominal GDP, quarterly, not seasonally adjusted", "domestic currency at current prices (as reported)", "IMF QNEA GDP at current prices, domestic currency, not seasonally adjusted."),
    ("gdp_real_lcu_quarterly_sa", "Real GDP, quarterly, seasonally adjusted", "chain-linked volume in domestic currency (as reported)", "IMF QNEA GDP at constant prices, domestic currency, seasonally adjusted; preserve IMF volume-index metadata."),
    ("gdp_real_lcu_quarterly_nsa", "Real GDP, quarterly, not seasonally adjusted", "chain-linked volume in domestic currency (as reported)", "IMF QNEA GDP at constant prices, domestic currency, not seasonally adjusted; preserve IMF volume-index metadata."),
    ("gdp_nominal_per_capita_lcu_quarterly_sa_estimate", "Nominal GDP per capita, quarterly, seasonally adjusted (estimated)", "current domestic currency per person per quarter", "Quarterly nominal GDP divided by World Bank annual population interpolated between mid-year observations (nearest reported value at series edges within one year); not an official quarterly per-capita series."),
    ("gdp_nominal_per_capita_lcu_quarterly_nsa_estimate", "Nominal GDP per capita, quarterly, not seasonally adjusted (estimated)", "current domestic currency per person per quarter", "Quarterly nominal GDP divided by World Bank annual population interpolated between mid-year observations (nearest reported value at series edges within one year); not an official quarterly per-capita series."),
    ("gdp_real_per_capita_lcu_quarterly_sa_estimate", "Real GDP per capita, quarterly, seasonally adjusted (estimated)", "chain-linked volume per person per quarter", "Quarterly real GDP divided by World Bank annual population interpolated between mid-year observations (nearest reported value at series edges within one year); not an official quarterly per-capita series."),
    ("gdp_real_per_capita_lcu_quarterly_nsa_estimate", "Real GDP per capita, quarterly, not seasonally adjusted (estimated)", "chain-linked volume per person per quarter", "Quarterly real GDP divided by World Bank annual population interpolated between mid-year observations (nearest reported value at series edges within one year); not an official quarterly per-capita series."),
    ("gdp_nominal_growth_yoy_pct_quarterly", "Nominal GDP growth, year over year (quarterly)", "percent", "Percent change from the same quarter one year earlier, using not-seasonally-adjusted current-price GDP."),
    ("gdp_real_growth_yoy_pct_quarterly", "Real GDP growth, year over year (quarterly)", "percent", "Percent change from the same quarter one year earlier, using not-seasonally-adjusted constant-price GDP."),
    ("gdp_nominal_per_capita_growth_yoy_pct_quarterly", "Nominal GDP per-capita growth, year over year (quarterly)", "percent", "Percent change from the same quarter one year earlier in estimated nominal GDP per capita."),
    ("gdp_real_per_capita_growth_yoy_pct_quarterly", "Real GDP per-capita growth, year over year (quarterly)", "percent", "Percent change from the same quarter one year earlier in estimated real GDP per capita."),
    ("gdp_nominal_growth_qoq_pct_quarterly_sa", "Nominal GDP growth, quarter over quarter (seasonally adjusted)", "percent", "Percent change from the previous quarter in seasonally adjusted nominal GDP; not annualized."),
    ("gdp_real_growth_qoq_pct_quarterly_sa", "Real GDP growth, quarter over quarter (seasonally adjusted)", "percent", "Percent change from the previous quarter in seasonally adjusted real GDP; not annualized."),
    ("gdp_nominal_per_capita_growth_qoq_pct_quarterly_sa", "Nominal GDP per-capita growth, quarter over quarter (seasonally adjusted)", "percent", "Percent change from the previous quarter in estimated seasonally adjusted nominal GDP per capita; not annualized."),
    ("gdp_real_per_capita_growth_qoq_pct_quarterly_sa", "Real GDP per-capita growth, quarter over quarter (seasonally adjusted)", "percent", "Percent change from the previous quarter in estimated seasonally adjusted real GDP per capita; not annualized."),
]

QUARTERLY_PRICE_INDICATORS = [
    ("cpi_index_all_items_quarterly_imf", "Consumer price index, quarterly mean (all items)", "index points (country reference period varies)", "Arithmetic mean of three monthly IMF all-items CPI index observations; complete quarters only. The index reference period varies by economy."),
    ("inflation_consumer_prices_yoy_pct_quarterly_imf", "CPI inflation, year over year (quarterly)", "percent", "Calculated as 100 * (quarterly mean CPI / quarterly mean CPI four quarters earlier - 1). CPI quarter means require all three monthly index values."),
    ("central_bank_policy_rate_pct_pa_quarterly_imf", "Central bank policy rate, quarter-end", "percent per annum", "Last reported monthly policy/central-bank rate in the quarter; source is IMF MFS interest rates. Monthly source values are not stored."),
    ("producer_price_index_quarterly_imf", "Producer price index, quarterly mean", "index points (reference period varies)", "Arithmetic mean of three monthly IMF producer-price index observations; complete quarters only. This is PPI, not WPI."),
    ("wholesale_price_index_quarterly", "Wholesale price index, quarterly mean (India)", "index points (2022-23=100)", "Arithmetic mean of three monthly all-commodities WPI values from India's Office of the Economic Adviser, base 2022-23=100. This release currently covers India from 2023 Q2 onward; later values may be provisional."),
]

IMF_SLUGS = {
    ("QNEA", "V", "SA"): "gdp_nominal_lcu_quarterly_sa",
    ("QNEA", "V", "NSA"): "gdp_nominal_lcu_quarterly_nsa",
    ("QNEA", "Q", "SA"): "gdp_real_lcu_quarterly_sa",
    ("QNEA", "Q", "NSA"): "gdp_real_lcu_quarterly_nsa",
}


def request_bytes(url: str, accept: str, attempts: int = 4) -> bytes:
    headers = {"Accept": accept, "User-Agent": USER_AGENT}
    imf_key = os.environ.get("IMF_API_SUBSCRIPTION_KEY")
    if imf_key and "api.imf.org" in url:
        headers["Ocp-Apim-Subscription-Key"] = imf_key
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == attempts - 1:
                raise RuntimeError(f"Could not fetch {url}: {exc}") from exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Could not fetch {url}")


def wb_json(url: str) -> Any:
    return json.loads(request_bytes(url, "application/json").decode("utf-8"))


def imf_xml(url: str) -> ET.Element:
    body = request_bytes(url, "application/vnd.sdmx.data+json;version=1.0.0")
    try:
        return ET.fromstring(body)
    except ET.ParseError as exc:
        raise RuntimeError(f"IMF response was not readable SDMX XML for {url}") from exc


def q(value: str) -> str:
    return urllib.parse.quote(value, safe="-_.~;:")


def get_countries() -> list[dict[str, Any]]:
    payload = wb_json(f"{WB_API}/country?format=json&per_page=400")
    countries = [row for row in payload[1] if row["region"]["value"].strip() != "Aggregates"]
    countries.sort(key=lambda row: row["id"])
    return countries


def wb_observations(codes: list[str], country_codes: set[str], end_year: int) -> tuple[list[dict[str, Any]], list[tuple[str, str, int, str]]]:
    code_path = ";".join(codes)
    per_page = 30000
    base = f"{WB_API}/country/all/indicator/{urllib.parse.quote(code_path, safe='.;') }?format=json&source=2&date={START_YEAR}:{end_year}&per_page={per_page}"
    first = wb_json(base + "&page=1")
    meta = first[0]
    all_rows = list(first[1] or [])
    for page in range(2, int(meta.get("pages", 1)) + 1):
        payload = wb_json(base + f"&page={page}")
        all_rows.extend(payload[1] or [])
    result = []
    for row in all_rows:
        country = row.get("countryiso3code") or row.get("country", {}).get("id")
        if country not in country_codes or row.get("value") is None:
            continue
        code = row.get("indicator", {}).get("id")
        if code not in WB_SERIES:
            continue
        result.append({
            "country": country,
            "code": code,
            "period": str(row["date"]),
            "value": float(row["value"]),
            "raw": str(row["value"]),
            "status": ("forecast" if row.get("obs_status") == "F" else "estimated" if row.get("obs_status") else "observed"),
            "metadata": {"obs_status": row.get("obs_status"), "decimal": row.get("decimal")},
        })
    return result, [("WB_WDI", base, len(all_rows), str(meta.get("lastupdated") or ""))]


def parse_imf_series(root: ET.Element) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for series in root.iter():
        if not series.tag.endswith("Series"):
            continue
        dims = dict(series.attrib)
        for obs in list(series):
            if not obs.tag.endswith("Obs"):
                continue
            attrs = dict(obs.attrib)
            if "OBS_VALUE" not in attrs or "TIME_PERIOD" not in attrs:
                continue
            try:
                val = float(attrs["OBS_VALUE"])
            except ValueError:
                continue
            if not math.isfinite(val):
                continue
            rows.append({"dims": dims, "period": attrs["TIME_PERIOD"], "value": val, "raw": attrs["OBS_VALUE"], "obs_attrs": attrs})
    return rows


def imf_request(flow: str, key: str, start: str, end: str) -> tuple[list[dict[str, Any]], str]:
    path = f"{IMF_API}/data/IMF.STA,{flow}/{key}"
    url = f"{path}?startPeriod={urllib.parse.quote(start)}&endPeriod={urllib.parse.quote(end)}"
    return parse_imf_series(imf_xml(url)), url


def create_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA synchronous=FULL")
    conn.executescript("""
    PRAGMA foreign_keys = ON;
    CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE countries (
        serial_no INTEGER PRIMARY KEY,
        wb_code TEXT NOT NULL UNIQUE,
        iso2_code TEXT NOT NULL,
        country_name TEXT NOT NULL,
        wb_region_code TEXT,
        wb_region TEXT,
        income_level_code TEXT,
        income_level TEXT,
        lending_type_code TEXT,
        lending_type TEXT
    );
    CREATE TABLE sources (
        source_id TEXT PRIMARY KEY,
        publisher TEXT NOT NULL,
        dataset_title TEXT NOT NULL,
        landing_url TEXT NOT NULL,
        api_url TEXT,
        terms TEXT NOT NULL,
        attribution TEXT NOT NULL,
        accessed_on TEXT NOT NULL
    );
    CREATE TABLE indicators (
        indicator_code TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        frequency TEXT NOT NULL,
        unit TEXT NOT NULL,
        definition TEXT NOT NULL,
        source_id TEXT REFERENCES sources(source_id),
        source_series_code TEXT,
        calculation TEXT,
        availability TEXT NOT NULL DEFAULT 'loaded'
    );
    CREATE TABLE source_snapshots (
        snapshot_id INTEGER PRIMARY KEY,
        source_id TEXT NOT NULL REFERENCES sources(source_id),
        retrieved_at TEXT NOT NULL,
        request_url TEXT NOT NULL,
        returned_rows INTEGER NOT NULL,
        provider_update_date TEXT,
        notes TEXT
    );
    CREATE TABLE source_series_metadata (
        country_code TEXT NOT NULL REFERENCES countries(wb_code),
        indicator_code TEXT NOT NULL REFERENCES indicators(indicator_code),
        source_series_code TEXT NOT NULL,
        source_id TEXT NOT NULL REFERENCES sources(source_id),
        seasonal_adjustment TEXT,
        series_metadata TEXT NOT NULL,
        PRIMARY KEY(country_code, indicator_code, source_series_code)
    );
    CREATE TABLE observations (
        country_code TEXT NOT NULL REFERENCES countries(wb_code),
        indicator_code TEXT NOT NULL REFERENCES indicators(indicator_code),
        period TEXT NOT NULL,
        frequency TEXT NOT NULL,
        value REAL NOT NULL,
        raw_value TEXT,
        value_status TEXT NOT NULL CHECK(value_status IN ('observed','estimated','derived','forecast','provisional')),
        source_id TEXT NOT NULL REFERENCES sources(source_id),
        source_series_code TEXT NOT NULL,
        seasonal_adjustment TEXT,
        observation_metadata TEXT,
        PRIMARY KEY(country_code, indicator_code, period, source_series_code)
    );
    CREATE INDEX idx_observations_period ON observations(period);
    CREATE INDEX idx_observations_indicator_period ON observations(indicator_code, period);
    CREATE INDEX idx_observations_country_indicator ON observations(country_code, indicator_code);
    CREATE VIEW indicator_coverage AS
        SELECT indicator_code, frequency, COUNT(*) AS observation_count,
               COUNT(DISTINCT country_code) AS economy_count,
               MIN(period) AS first_period, MAX(period) AS last_period
        FROM observations GROUP BY indicator_code, frequency;
    CREATE VIEW research_observations AS
        SELECT c.serial_no, c.wb_code, c.country_name, c.wb_region, c.income_level,
               i.indicator_code, i.display_name, o.period, o.frequency, o.value,
               i.unit, o.value_status, o.seasonal_adjustment, o.source_id,
               o.source_series_code, o.observation_metadata
        FROM observations o
        JOIN countries c ON c.wb_code=o.country_code
        JOIN indicators i ON i.indicator_code=o.indicator_code;
    """)
    return conn


def publish_database(conn: sqlite3.Connection, building_path: Path, output_path: Path) -> None:
    """Close, validate, then atomically replace the last good snapshot."""
    conn.execute("PRAGMA optimize")
    conn.close()
    check = sqlite3.connect(building_path)
    integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
    check.close()
    if integrity != "ok":
        raise RuntimeError(f"SQLite integrity check failed: {integrity}")
    building_path.replace(output_path)


def export_release(database_path: Path) -> tuple[Path, Path, Path]:
    """Write atomic compressed and CSV companions for a published SQLite snapshot."""
    database_path = database_path.resolve()
    parent = database_path.parent
    stem = database_path.stem
    gzip_path = parent / f"{database_path.name}.gz"
    latest_path = parent / f"{stem}_latest.csv"
    all_path = parent / f"{stem}_all_observations.csv.gz"
    gzip_building = gzip_path.with_name(gzip_path.name + ".building")
    latest_building = latest_path.with_name(latest_path.name + ".building")
    all_building = all_path.with_name(all_path.name + ".building")

    with database_path.open("rb") as src, gzip_building.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", compresslevel=9, mtime=0) as compressed:
            shutil.copyfileobj(src, compressed, length=1024 * 1024)

    con = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    latest_query = """
        WITH ranked AS (
            SELECT r.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY wb_code, indicator_code ORDER BY period DESC
                   ) AS rn
            FROM research_observations AS r
        )
        SELECT country_name, wb_code, wb_region, income_level, display_name,
               indicator_code, period, frequency, value, unit, value_status,
               source_id, source_series_code
        FROM ranked WHERE rn=1
        ORDER BY country_name, indicator_code
    """
    all_query = """
        SELECT serial_no, wb_code, country_name, wb_region, income_level,
               indicator_code, display_name, period, frequency, value, unit,
               value_status, seasonal_adjustment, source_id, source_series_code,
               observation_metadata
        FROM research_observations
        ORDER BY wb_code, indicator_code, period
    """
    latest_headers = [
        "country_name", "wb_code", "wb_region", "income_level", "indicator",
        "indicator_code", "latest_available_period", "frequency", "value", "unit",
        "value_status", "source_id", "source_series_code",
    ]
    try:
        with latest_building.open("w", encoding="utf-8-sig", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(latest_headers)
            writer.writerows(con.execute(latest_query))

        with all_building.open("wb") as raw:
            with gzip.GzipFile(filename="", fileobj=raw, mode="wb", compresslevel=9, mtime=0) as compressed:
                text = io.TextIOWrapper(compressed, encoding="utf-8", newline="")
                writer = csv.writer(text, lineterminator="\n")
                cursor = con.execute(all_query)
                writer.writerow([column[0] for column in cursor.description])
                writer.writerows(cursor)
                text.flush()
                text.detach()
    finally:
        con.close()

    gzip_building.replace(gzip_path)
    latest_building.replace(latest_path)
    all_building.replace(all_path)
    return gzip_path, latest_path, all_path


def quarter_index(period: str) -> int:
    year, quarter = period.split("-Q")
    return int(year) * 4 + int(quarter) - 1


def quarter_pop(pop: dict[int, float], period: str) -> float | None:
    year, quarter = period.split("-Q")
    y = int(year)
    qn = int(quarter)
    target = y + (qn - 0.5) / 4.0
    points = sorted((yr + 0.5, value) for yr, value in pop.items())
    if not points:
        return None
    if target <= points[0][0]:
        return points[0][1] if points[0][0] - target <= 0.5 else None
    if target >= points[-1][0]:
        return points[-1][1] if target - points[-1][0] <= 1.0 else None
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t0 <= target <= t1:
            weight = (target - t0) / (t1 - t0)
            return v0 + weight * (v1 - v0)
    return None


def month_to_quarter(period: str) -> str:
    year, month = period.split("-M")
    m = int(month)
    return f"{year}-Q{(m - 1) // 3 + 1}"


def quarter_lag(period: str, lag: int) -> str:
    year, quarter = period.split("-Q")
    index = int(year) * 4 + int(quarter) - 1 - lag
    prior_year, remainder = divmod(index, 4)
    return f"{prior_year}-Q{remainder + 1}"


def public_imf_row(row: dict[str, Any]) -> bool:
    attrs = row.get("obs_attrs", {})
    sharing = attrs.get("ACCESS_SHARING_LEVEL")
    security = attrs.get("SECURITY_CLASSIFICATION")
    return (sharing in (None, "PUBLIC_OPEN")) and (security in (None, "PUB"))


def aggregate_imf_monthly(rows: list[dict[str, Any]], country_codes: set[str], method: str) -> list[dict[str, Any]]:
    """Turn monthly IMF source rows into quarterly values without storing monthly observations."""
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        dims = row["dims"]
        country = dims.get("COUNTRY")
        if country not in country_codes or not public_imf_row(row):
            continue
        period = row["period"]
        if "-M" not in period:
            continue
        series_dims = {k: v for k, v in dims.items() if k != "COUNTRY"}
        series_base = "|".join(f"{k}={series_dims[k]}" for k in sorted(series_dims))
        grouped[(country, series_base, month_to_quarter(period))].append(row)

    out: list[dict[str, Any]] = []
    for (country, series_base, quarter), values in grouped.items():
        by_month = {row["period"]: row for row in values}
        ordered_periods = sorted(by_month)
        if method == "quarterly_mean":
            year, q = quarter.split("-Q")
            first_month = (int(q) - 1) * 3 + 1
            expected = [f"{year}-M{m:02d}" for m in range(first_month, first_month + 3)]
            if any(m not in by_month for m in expected):
                continue
            source_periods = expected
            selected = [by_month[m] for m in expected]
            value = sum(r["value"] for r in selected) / 3
        elif method == "quarter_end":
            if not ordered_periods:
                continue
            source_periods = [ordered_periods[-1]]
            selected = [by_month[source_periods[0]]]
            value = selected[0]["value"]
        else:
            raise ValueError(f"Unsupported monthly-to-quarterly method: {method}")
        sample = selected[-1]
        dims = sample["dims"]
        source_code = f"IMF|{series_base}|aggregation={method}"
        estimated = any(r["obs_attrs"].get("DERIVATION_TYPE", "O") != "O" for r in selected)
        metadata = {
            "aggregation_method": method,
            "source_months": source_periods,
            "source_observation_count": len(selected),
            "source_series_dimensions": dims,
            "source_derivation_types": [r["obs_attrs"].get("DERIVATION_TYPE", "O") for r in selected],
        }
        out.append({
            "country": country,
            "period": quarter,
            "value": value,
            "raw": None,
            "status": "estimated" if estimated else "derived",
            "series_code": source_code,
            "dims": dims,
            "metadata": metadata,
        })
    return out


def add_quarterly_cpi_inflation(conn: sqlite3.Connection, records: list[dict[str, Any]]) -> int:
    levels: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for row in records:
        levels[(row["country"], row["series_code"])][row["period"]] = row["value"]
    inserted = 0
    for (country, source_code), values in levels.items():
        for period, value in values.items():
            prior = values.get(quarter_lag(period, 4))
            if prior is None or prior == 0:
                continue
            out_code = f"derived_yoy:{source_code}"
            add_observation(conn, country=country, indicator="inflation_consumer_prices_yoy_pct_quarterly_imf",
                            period=period, frequency="quarterly", value=(value / prior - 1) * 100,
                            raw=None, status="derived", source="IMF_CPI", series_code=out_code,
                            metadata={"formula":"100 * (quarterly_mean_cpi / same_quarter_prior_year_mean_cpi - 1)",
                                      "source_cpi_series_code":source_code,"comparison_period":quarter_lag(period,4)})
            inserted += 1
    return inserted


def xlsx_first_sheet_rows(body: bytes) -> list[list[str | None]]:
    """Read a simple first worksheet from an .xlsx file using only the standard library."""
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        first_sheet = next(workbook.iter(f"{{{main_ns}}}sheet"))
        relation_id = first_sheet.attrib[f"{{{rel_ns}}}id"]
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(r.attrib["Target"] for r in relations.iter(f"{{{pkg_rel_ns}}}Relationship") if r.attrib["Id"] == relation_id)
        sheet_path = posixpath.normpath(posixpath.join("xl", target))
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in strings.iter(f"{{{main_ns}}}si"):
                shared.append("".join(t.text or "" for t in item.iter(f"{{{main_ns}}}t")))
        sheet = ET.fromstring(archive.read(sheet_path))
        rows: list[list[str | None]] = []
        for row in sheet.iter(f"{{{main_ns}}}row"):
            cells: dict[int, str | None] = {}
            for cell in row.iter(f"{{{main_ns}}}c"):
                ref = cell.attrib.get("r", "")
                letters = "".join(ch for ch in ref if ch.isalpha())
                column = 0
                for ch in letters:
                    column = column * 26 + ord(ch.upper()) - 64
                value_node = cell.find(f"{{{main_ns}}}v")
                if cell.attrib.get("t") == "inlineStr":
                    value = "".join(t.text or "" for t in cell.iter(f"{{{main_ns}}}t"))
                elif value_node is None:
                    value = None
                elif cell.attrib.get("t") == "s":
                    value = shared[int(value_node.text or "0")]
                else:
                    value = value_node.text
                cells[column] = value
            if cells:
                rows.append([cells.get(i) for i in range(1, max(cells) + 1)])
        return rows


class OEAWpiLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href and "wpi_monthly_index" in href.lower() and href.lower().endswith(".xlsx"):
            self.links.append(href)


def fetch_india_wpi_quarterly() -> tuple[list[dict[str, Any]], str, int]:
    page_url = "https://eaindustry.nic.in/download_data_2223.asp"
    html = request_bytes(page_url, "text/html; charset=utf-8").decode("utf-8", "replace")
    parser = OEAWpiLinkParser()
    parser.feed(html)
    if not parser.links:
        raise RuntimeError("Office of the Economic Adviser WPI workbook link was not found.")
    file_url = urllib.parse.urljoin(page_url, parser.links[0])
    body = request_bytes(file_url, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    rows = xlsx_first_sheet_rows(body)
    if not rows or len(rows[0]) < 5:
        raise RuntimeError("Office of the Economic Adviser WPI workbook has an unexpected layout.")
    headers = rows[0]
    all_row = next((row for row in rows[1:] if len(row) >= 3 and row[2] == "1000000000"), None)
    if all_row is None:
        raise RuntimeError("All-commodities WPI row was not found in the official workbook.")
    monthly: dict[str, float] = {}
    for i, header in enumerate(headers[4:], start=4):
        if not header or i >= len(all_row) or all_row[i] in (None, ""):
            continue
        try:
            date = dt.datetime.strptime(str(header), "%b-%y")
            monthly[f"{date.year}-M{date.month:02d}"] = float(all_row[i])
        except (ValueError, TypeError):
            continue
    by_quarter: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for period, value in monthly.items():
        by_quarter[month_to_quarter(period)].append((period, value))
    ordered_months = sorted(monthly)
    provisional_months = set(ordered_months[-2:])
    result = []
    for quarter, entries in sorted(by_quarter.items()):
        if len(entries) != 3:
            continue
        entries.sort()
        result.append({
            "country": "IND",
            "period": quarter,
            "value": sum(v for _, v in entries) / 3,
            "raw": None,
            "status": "provisional" if any(m in provisional_months for m, _ in entries) else "derived",
            "series_code": "OEA_WPI|ALL_COMMODITIES|2022-23=100|quarterly_mean",
            "metadata": {"source_months":[m for m, _ in entries],"aggregation_method":"arithmetic_mean",
                         "source_row_code":"1000000000","base_period":"2022-23=100",
                         "provisional_months":sorted(provisional_months.intersection(m for m, _ in entries))},
        })
    return result, file_url, len(monthly)


def add_indicator(conn: sqlite3.Connection, code: str, name: str, frequency: str, unit: str, definition: str, source_id: str | None, series_code: str | None, calculation: str | None = None, availability: str = "loaded") -> None:
    conn.execute("INSERT OR REPLACE INTO indicators VALUES(?,?,?,?,?,?,?,?,?)", (code,name,frequency,unit,definition,source_id,series_code,calculation,availability))


def add_observation(conn: sqlite3.Connection, *, country: str, indicator: str, period: str, frequency: str, value: float, raw: str | None, status: str, source: str, series_code: str, seasonal: str | None = None, metadata: dict[str, Any] | None = None, series_metadata: dict[str, Any] | None = None) -> None:
    if not math.isfinite(value):
        return
    if series_metadata is not None:
        conn.execute("""INSERT OR REPLACE INTO source_series_metadata
            (country_code,indicator_code,source_series_code,source_id,seasonal_adjustment,series_metadata)
            VALUES(?,?,?,?,?,?)""",
            (country,indicator,series_code,source,seasonal,json.dumps(series_metadata,ensure_ascii=False,sort_keys=True)))
    conn.execute("""INSERT OR REPLACE INTO observations
        (country_code,indicator_code,period,frequency,value,raw_value,value_status,source_id,source_series_code,seasonal_adjustment,observation_metadata)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (country,indicator,period,frequency,value,raw,status,source,series_code,seasonal,
         json.dumps(metadata,ensure_ascii=False,sort_keys=True) if metadata else None))


def main() -> int:
    global START_YEAR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("database/macro_research.sqlite"), help="SQLite output path (default: database/macro_research.sqlite)")
    parser.add_argument("--start-year", type=int, default=START_YEAR, help="First year/quarter/month to retrieve (default: 2000)")
    parser.add_argument("--annual-only", action="store_true", help="Fetch annual World Bank data only; omit quarterly IMF and India WPI series")
    args = parser.parse_args()
    START_YEAR = args.start_year
    args.output.parent.mkdir(parents=True, exist_ok=True)
    building_path = args.output.with_name(args.output.name + ".building")
    if building_path.exists():
        building_path.unlink()
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    end_year = dt.date.today().year
    end_month = dt.date.today().month
    countries = get_countries()
    country_codes = {row["id"] for row in countries}
    print(f"World Bank country/economy rows: {len(countries)}", flush=True)

    conn = create_database(building_path)
    conn.executemany("INSERT INTO countries VALUES(?,?,?,?,?,?,?,?,?,?)", [
        (i,row["id"],row["iso2Code"],row["name"],row["region"]["id"],row["region"]["value"].strip(),row["incomeLevel"]["id"],row["incomeLevel"]["value"].strip(),row["lendingType"]["id"],row["lendingType"]["value"].strip())
        for i,row in enumerate(countries,1)
    ])
    source_rows = [
        ("WB_WDI","World Bank","World Development Indicators","https://datacatalog.worldbank.org/search/dataset/0037712/world-development-indicators",WB_API,"CC BY 4.0","Source: World Bank, World Development Indicators, indicator codes shown in the database. Licensed under CC BY 4.0.",AS_OF),
        ("IMF_QNEA","International Monetary Fund","National Economic Accounts (NEA), Quarterly Data","https://data.imf.org/en/datasets/IMF.STA%3AQNEA",f"{IMF_API}/data/IMF.STA,QNEA","IMF statistical-data use terms; cite IMF and dataset; preserve any third-party attribution.","Source: International Monetary Fund, National Economic Accounts (NEA), Quarterly Data.",AS_OF),
        ("IMF_CPI","International Monetary Fund","Consumer Price Index (CPI)","https://data.imf.org/en/datasets/IMF.STA%3ACPI",f"{IMF_API}/data/IMF.STA,CPI","IMF statistical-data use terms; cite IMF and dataset; preserve any third-party attribution.","Source: International Monetary Fund, Consumer Price Index (CPI).",AS_OF),
        ("IMF_MFS_IR","International Monetary Fund","Monetary and Financial Statistics (MFS), Interest Rate","https://data.imf.org/en/datasets/IMF.STA%3AMFS_IR",f"{IMF_API}/data/IMF.STA,MFS_IR","IMF statistical-data use terms; cite IMF and dataset; preserve any third-party attribution.","Source: International Monetary Fund, Monetary and Financial Statistics (MFS), Interest Rate.",AS_OF),
        ("IMF_PPI","International Monetary Fund","Producer Price Index (PPI)","https://data.imf.org/en/datasets/IMF.STA%3APPI",f"{IMF_API}/data/IMF.STA,PPI","IMF statistical-data use terms; cite IMF and dataset; preserve any third-party attribution.","Source: International Monetary Fund, Producer Price Index (PPI). This is not a wholesale price index.",AS_OF),
        ("IN_OEA_WPI","Government of India, Office of the Economic Adviser","Wholesale Price Index, base 2022-23","https://eaindustry.nic.in/download_data_2223.asp","https://eaindustry.nic.in/indx_download_2223/","Government of India source; consult the publisher's reuse terms before redistribution.","Source: Office of the Economic Adviser, DPIIT, Government of India, WPI base 2022-23.",AS_OF),
    ]
    conn.executemany("INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)", source_rows)
    conn.execute("INSERT INTO schema_meta VALUES('schema_version','1.0')")
    conn.execute("INSERT INTO schema_meta VALUES('release_date',?)", (AS_OF,))
    conn.execute("INSERT INTO schema_meta VALUES('historical_start',?)", (str(START_YEAR),))
    conn.execute("INSERT INTO schema_meta VALUES('country_source_order','World Bank three-letter code order')")
    conn.commit()

    # Catalog entries for World Bank indicators.
    wb_slug_by_code = {}
    for code, info in WB_SERIES.items():
        wb_slug_by_code[code] = info["slug"]
        add_indicator(conn, info["slug"], info["name"], "annual", info["unit"], info["description"], "WB_WDI", code,
                      "World Bank Indicators API, source=2 (WDI); calendar-year observation.")
    for code, name, unit, definition in DERIVED_INDICATORS:
        add_indicator(conn, code, name, "quarterly" if "quarterly" in code else "annual", unit, definition,
                      "IMF_QNEA" if "quarterly" in code else "WB_WDI", None, definition)
    for code,name,unit,definition in QUARTERLY_PRICE_INDICATORS[:4]:
        source = "IMF_CPI" if code.startswith("cpi_") or code.startswith("inflation_") else "IMF_MFS_IR" if code.startswith("central_bank_") else "IMF_PPI"
        series = "CPI._T.IX.M" if code.startswith("cpi_") or code.startswith("inflation_") else "MFS166_RT_PT_A_PT.M" if code.startswith("central_bank_") else "PPI.IX.M"
        add_indicator(conn,code,name,"quarterly",unit,definition,source,series,definition)
    add_indicator(conn,QUARTERLY_PRICE_INDICATORS[4][0],QUARTERLY_PRICE_INDICATORS[4][1],"quarterly",
                  QUARTERLY_PRICE_INDICATORS[4][2],QUARTERLY_PRICE_INDICATORS[4][3],"IN_OEA_WPI",
                  "OEA_WPI|ALL_COMMODITIES|2022-23=100","Arithmetic mean of monthly WPI observations; complete quarters only.")

    wb_codes = list(WB_SERIES)
    wb_data, wb_snapshots = wb_observations(wb_codes, country_codes, end_year)
    for rec in wb_data:
        info = WB_SERIES[rec["code"]]
        add_observation(conn,country=rec["country"],indicator=info["slug"],period=rec["period"],frequency="annual",value=rec["value"],raw=rec["raw"],status=rec["status"],source="WB_WDI",series_code=rec["code"],metadata=rec["metadata"])
    conn.executemany("INSERT INTO source_snapshots(source_id,retrieved_at,request_url,returned_rows,provider_update_date,notes) VALUES(?,?,?,?,?,?)",
                     [(sid,now,url,n,updated,"World Bank API page query; aggregates filtered to WDI country/economy list.") for sid,url,n,updated in wb_snapshots])
    conn.commit()
    print(f"World Bank observations loaded: {len(wb_data):,}", flush=True)

    # Preserve raw annual inputs for calculated nominal growth and quarterly per-capita estimates.
    wb_values: dict[tuple[str,str], dict[int,float]] = defaultdict(dict)
    for rec in wb_data:
        try:
            year = int(rec["period"])
        except ValueError:
            continue
        wb_values[(rec["country"],rec["code"])][year] = rec["value"]

    # Annual nominal growth is calculated in local currency, avoiding exchange-rate-driven USD changes.
    derived_pairs = [
        ("NY.GDP.MKTP.CN","gdp_nominal_growth_yoy_pct_annual_lcu"),
        ("NY.GDP.PCAP.CN","gdp_per_capita_nominal_growth_yoy_pct_annual_lcu"),
    ]
    for (country, code), values in wb_values.items():
        for input_code, out_code in derived_pairs:
            if code != input_code:
                continue
            for year, val in values.items():
                previous = values.get(year-1)
                if previous is None or previous == 0:
                    continue
                result = (val / previous - 1.0) * 100.0
                add_observation(conn,country=country,indicator=out_code,period=str(year),frequency="annual",value=result,raw=None,status="derived",source="WB_WDI",series_code=f"calculated:{input_code}:year_over_year",metadata={"formula":"100 * (current_year / prior_year - 1)","nominal_growth_basis":"current local currency"})
    conn.commit()

    if args.annual_only:
        conn.execute("UPDATE indicators SET availability='not_fetched_annual_only' WHERE source_id LIKE 'IMF_%' OR source_id='IN_OEA_WPI'")
        for source_id,url in [
            ("IMF_QNEA","https://data.imf.org/en/datasets/IMF.STA%3AQNEA"),
            ("IMF_CPI","https://data.imf.org/en/datasets/IMF.STA%3ACPI"),
            ("IMF_MFS_IR","https://data.imf.org/en/datasets/IMF.STA%3AMFS_IR"),
            ("IMF_PPI","https://data.imf.org/en/datasets/IMF.STA%3APPI"),
            ("IN_OEA_WPI","https://eaindustry.nic.in/download_data_2223.asp"),
        ]:
            conn.execute("INSERT INTO source_snapshots(source_id,retrieved_at,request_url,returned_rows,provider_update_date,notes) VALUES(?,?,?,?,?,?)",(source_id,now,url,0,None,"Skipped because --annual-only was selected."))
        conn.execute("INSERT INTO schema_meta VALUES('frequency_policy','Annual WDI observations from 2000 only; quarterly IMF and India WPI series omitted by --annual-only.')")
        conn.execute("INSERT INTO schema_meta VALUES('gap_policy','No zero-fill or unlabelled interpolation. Annual poverty observations retain their survey-based observation years.')")
        conn.commit()
        publish_database(conn,building_path,args.output)
        print(f"SQLite release saved: {args.output}", flush=True)
        exports = export_release(args.output)
        print("Companion files saved: " + ", ".join(str(path) for path in exports), flush=True)
        print("Annual WDI data are populated; quarterly data were skipped by request.", flush=True)
        return 0

    # IMF QNEA: nominal (V) and real chain-volume (Q), in domestic currency.
    end_quarter = 4 if end_month in (10,11,12) else (end_month-1)//3 + 1
    q_end = f"{end_year}-Q{end_quarter}"
    q_start = f"{START_YEAR}-Q1"
    qne_records: list[dict[str,Any]] = []
    qne_snapshots = []
    qne_defs = [("V","SA"),("V","NSA"),("Q","SA"),("Q","NSA")]
    for price_type, adjustment in qne_defs:
        key=f".B1GQ.{price_type}.{adjustment}.XDC.Q"
        rows,url=imf_request("QNEA",key,q_start,q_end)
        qne_snapshots.append(("IMF_QNEA",now,url,len(rows),None,f"QNEA GDP; PRICE_TYPE={price_type}; S_ADJUSTMENT={adjustment}; XDC; Q."))
        slug=IMF_SLUGS[("QNEA",price_type,adjustment)]
        for row in rows:
            dims=row["dims"]
            country=dims.get("COUNTRY")
            if country not in country_codes or not public_imf_row(row):
                continue
            series_code=f"QNEA|{dims.get('INDICATOR')}|{price_type}|{adjustment}|{dims.get('TYPE_OF_TRANSFORMATION')}|{dims.get('FREQUENCY')}"
            attrs={k:v for k,v in row["obs_attrs"].items() if k not in ("TIME_PERIOD","OBS_VALUE")}
            qne_status="observed" if attrs.get("DERIVATION_TYPE","O")=="O" else "estimated"
            add_observation(conn,country=country,indicator=slug,period=row["period"],frequency="quarterly",value=row["value"],raw=row["raw"],status=qne_status,source="IMF_QNEA",series_code=series_code,seasonal=adjustment,metadata=attrs,series_metadata=dims)
            qne_records.append({"country":country,"slug":slug,"period":row["period"],"value":row["value"],"series_code":series_code,"seasonal":adjustment})
    conn.executemany("INSERT INTO source_snapshots(source_id,retrieved_at,request_url,returned_rows,provider_update_date,notes) VALUES(?,?,?,?,?,?)",qne_snapshots)
    conn.commit()
    print(f"IMF quarterly GDP observations loaded: {len(qne_records):,}", flush=True)

    # Estimate quarterly per-capita levels by dividing GDP by linearly interpolated annual mid-year population.
    population_by_country = {country: wb_values.get((country,"SP.POP.TOTL"),{}) for country in country_codes}
    q_levels: dict[tuple[str,str,str],dict[str,float]] = defaultdict(dict)
    q_meta: dict[tuple[str,str,str],dict[str,Any]] = {}
    for rec in qne_records:
        q_levels[(rec["country"],rec["slug"],rec["seasonal"])][rec["period"]]=rec["value"]
        q_meta[(rec["country"],rec["slug"],rec["seasonal"])]=rec
    pc_slug = {
        ("gdp_nominal_lcu_quarterly_sa","SA"):"gdp_nominal_per_capita_lcu_quarterly_sa_estimate",
        ("gdp_nominal_lcu_quarterly_nsa","NSA"):"gdp_nominal_per_capita_lcu_quarterly_nsa_estimate",
        ("gdp_real_lcu_quarterly_sa","SA"):"gdp_real_per_capita_lcu_quarterly_sa_estimate",
        ("gdp_real_lcu_quarterly_nsa","NSA"):"gdp_real_per_capita_lcu_quarterly_nsa_estimate",
    }
    pc_levels: dict[tuple[str,str],dict[str,float]] = defaultdict(dict)
    for (country,slug,adjustment), values in q_levels.items():
        out_slug=pc_slug[(slug,adjustment)]
        for period,value in values.items():
            population=quarter_pop(population_by_country.get(country,{}),period)
            if not population or population <= 0:
                continue
            pc_value=value/population
            source_rec=q_meta[(country,slug,adjustment)]
            series_code=f"derived_per_capita|{source_rec['series_code']}|population=SP.POP.TOTL_interpolated"
            add_observation(conn,country=country,indicator=out_slug,period=period,frequency="quarterly",value=pc_value,raw=None,status="estimated",source="IMF_QNEA",series_code=series_code,seasonal=adjustment)
            pc_levels[(country,out_slug)][period]=pc_value

    def derive_quarter_growth(slug: str, result_slug: str, lag: int, suffix: str) -> None:
        if "per_capita" in slug:
            items = [(country, base_slug, values) for (country, base_slug), values in pc_levels.items() if base_slug == slug]
        else:
            items = [(country, base_slug, values) for (country, base_slug, adjustment), values in q_levels.items() if base_slug == slug and adjustment == suffix]
        for country, base_slug, values in items:
            for period,value in values.items():
                index=quarter_index(period)
                target=index-lag
                prev_year,rem=divmod(target,4)
                prev_period=f"{prev_year}-Q{rem+1}"
                old=values.get(prev_period)
                if old is None or old==0:
                    continue
                source_id="IMF_QNEA"
                basis="same quarter prior year" if lag==4 else "previous quarter"
                key=f"derived:{slug}:{basis}:{suffix}"
                add_observation(conn,country=country,indicator=result_slug,period=period,frequency="quarterly",value=(value/old-1)*100,raw=None,status="derived",source=source_id,series_code=key,seasonal=suffix)

    # Same-quarter-year growth uses NSA levels; quarter-over-quarter growth uses SA levels.
    for base,out in [
        ("gdp_nominal_lcu_quarterly_nsa","gdp_nominal_growth_yoy_pct_quarterly"),
        ("gdp_real_lcu_quarterly_nsa","gdp_real_growth_yoy_pct_quarterly"),
    ]:
        derive_quarter_growth(base,out,4,"NSA")
    for base,out in [
        ("gdp_nominal_per_capita_lcu_quarterly_nsa_estimate","gdp_nominal_per_capita_growth_yoy_pct_quarterly"),
        ("gdp_real_per_capita_lcu_quarterly_nsa_estimate","gdp_real_per_capita_growth_yoy_pct_quarterly"),
    ]:
        derive_quarter_growth(base,out,4,"NSA")
    for base,out in [
        ("gdp_nominal_lcu_quarterly_sa","gdp_nominal_growth_qoq_pct_quarterly_sa"),
        ("gdp_real_lcu_quarterly_sa","gdp_real_growth_qoq_pct_quarterly_sa"),
    ]:
        derive_quarter_growth(base,out,1,"SA")
    for base,out in [
        ("gdp_nominal_per_capita_lcu_quarterly_sa_estimate","gdp_nominal_per_capita_growth_qoq_pct_quarterly_sa"),
        ("gdp_real_per_capita_lcu_quarterly_sa_estimate","gdp_real_per_capita_growth_qoq_pct_quarterly_sa"),
    ]:
        derive_quarter_growth(base,out,1,"SA")
    conn.commit()

    # Fetch monthly source files, aggregate them, and store quarterly observations only.
    month_end=f"{end_year}-M{end_month:02d}"
    month_start=f"{START_YEAR}-M01"
    cpi_monthly,cpi_url=imf_request("CPI",".CPI._T.IX.M",month_start,month_end)
    cpi_quarterly=aggregate_imf_monthly(cpi_monthly,country_codes,"quarterly_mean")
    for row in cpi_quarterly:
        add_observation(conn,country=row["country"],indicator="cpi_index_all_items_quarterly_imf",period=row["period"],
                        frequency="quarterly",value=row["value"],raw=None,status=row["status"],source="IMF_CPI",
                        series_code=row["series_code"],metadata=row["metadata"],
                        series_metadata={**row["dims"],"quarterly_aggregation":"arithmetic_mean_of_three_months"})
    cpi_inflation_count=add_quarterly_cpi_inflation(conn,cpi_quarterly)
    conn.execute("INSERT INTO source_snapshots(source_id,retrieved_at,request_url,returned_rows,provider_update_date,notes) VALUES(?,?,?,?,?,?)",
                 ("IMF_CPI",now,cpi_url,len(cpi_monthly),None,"Monthly all-items CPI fetched from IMF; three observations averaged per quarter. Monthly values are not stored."))
    conn.commit()
    print(f"IMF quarterly CPI observations loaded: {len(cpi_quarterly):,}; derived quarterly inflation: {cpi_inflation_count:,}", flush=True)

    # Quarter-end policy rate and quarterly mean PPI; no monthly observations enter SQLite.
    high_freq=[
        ("MFS_IR",".MFS166_RT_PT_A_PT.M","central_bank_policy_rate_pct_pa_quarterly_imf","IMF_MFS_IR","quarter_end","Central bank policy rate: last reported monthly value in each quarter."),
        ("PPI",".PPI.IX.M","producer_price_index_quarterly_imf","IMF_PPI","quarterly_mean","Producer price index: mean of three monthly index values; separate from WPI."),
    ]
    for flow,key,slug,source,method,note in high_freq:
        rows,url=imf_request(flow,key,month_start,month_end)
        quarterly=aggregate_imf_monthly(rows,country_codes,method)
        for row in quarterly:
            add_observation(conn,country=row["country"],indicator=slug,period=row["period"],frequency="quarterly",
                            value=row["value"],raw=None,status=row["status"],source=source,series_code=row["series_code"],
                            metadata=row["metadata"],series_metadata={**row["dims"],"quarterly_aggregation":method})
        conn.execute("INSERT INTO source_snapshots(source_id,retrieved_at,request_url,returned_rows,provider_update_date,notes) VALUES(?,?,?,?,?,?)",
                     (source,now,url,len(rows),None,f"{note} Monthly source observations fetched: {len(rows)}; only quarterly outputs are stored."))
        conn.commit()
        print(f"{flow} quarterly observations loaded: {len(quarterly):,}", flush=True)

    # India WPI is published monthly; aggregate the all-commodities row to quarters.
    wpi_quarterly,wpi_url,wpi_month_count=fetch_india_wpi_quarterly()
    for row in wpi_quarterly:
        add_observation(conn,country=row["country"],indicator="wholesale_price_index_quarterly",period=row["period"],
                        frequency="quarterly",value=row["value"],raw=None,status=row["status"],source="IN_OEA_WPI",
                        series_code=row["series_code"],metadata=row["metadata"],
                        series_metadata={"source":"Office of the Economic Adviser, DPIIT, Government of India",
                                         "base_period":"2022-23=100","source_row_code":"1000000000"})
    conn.execute("INSERT INTO source_snapshots(source_id,retrieved_at,request_url,returned_rows,provider_update_date,notes) VALUES(?,?,?,?,?,?)",
                 ("IN_OEA_WPI",now,wpi_url,wpi_month_count,None,"Official WPI workbook downloaded; all-commodities monthly index aggregated to complete calendar quarters. Monthly values are not stored."))

    # Indicators are considered loaded only when the refreshed snapshot contains observations.
    conn.execute("""UPDATE indicators SET availability=CASE
                  WHEN EXISTS (SELECT 1 FROM observations o WHERE o.indicator_code=indicators.indicator_code)
                  THEN 'loaded' ELSE 'no_source_observations' END
                  WHERE source_id IN ('IMF_QNEA','IMF_CPI','IMF_MFS_IR','IMF_PPI','IN_OEA_WPI')""")
    # No monthly observations are stored. Absence is unavailable, never zero-filled.
    conn.execute("INSERT INTO schema_meta VALUES('retrieved_at_utc',?)", (now,))
    conn.execute("INSERT INTO schema_meta VALUES('frequency_policy','Annual WDI indicators from 2000; IMF quarterly GDP and quarterly price/rate series where reported; monthly IMF CPI, policy-rate and PPI source observations are aggregated and not stored; India WPI is quarterly from the official 2022-23 base series.')")
    conn.execute("INSERT INTO schema_meta VALUES('gap_policy','No zero-fill or unlabelled interpolation. CPI/PPI/WPI quarterly means require three monthly source observations; quarter-end policy rates use the latest reported month in each quarter. Quarterly GDP per capita is estimated from annual population interpolation. Poverty observations remain survey-year based.')")
    conn.commit()
    publish_database(conn,building_path,args.output)
    print(f"SQLite release saved: {args.output}", flush=True)
    exports = export_release(args.output)
    print("Companion files saved: " + ", ".join(str(path) for path in exports), flush=True)
    print("Economy counts and actual date ranges are available in the indicator_coverage view.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, urllib.error.URLError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

# Economics Society macroeconomic research database

This repository contains a portable SQLite snapshot for research, two CSV companions, and the script that rebuilds the source data, derived indicators, and export files. The release was retrieved on **2026-09-29**.

## Current release

- **217 World Bank country/economy entries** with World Bank and ISO-2 codes, region, income group, and lending type.
- **40 populated indicators:** 19 annual series and 21 quarterly series.
- **263,863 observations:** 96,475 annual and 167,388 quarterly.
- Data start in 2000. WDI annual series currently extend through 2025; the latest quarterly dates vary by source and series.
- Stored observations use **annual or quarterly frequency only**. Monthly input values are aggregated and discarded during refresh; there are no monthly observation rows.

The country table follows World Bank's country/economy catalogue, which includes some territories and other economies in addition to sovereign states. `serial_no` is a convenient row number, not a ranking or permanent identifier. Use `wb_code` to join country records.

## Files

- `macro_research.sqlite.gz.part00` through `.part02` — the compressed SQLite snapshot split into three files for reliable repository transfer. Join the parts in order before extracting.
- `macro_research_all_observations.csv.gz` — single-file compressed CSV of every observation; useful when a spreadsheet or phone is easier than SQLite.
- `macro_research_latest.csv` — one latest available observation per country and indicator. It is a quick-view file, **not** the full history.
- `scripts/refresh_macro_database.py` — reproducible source refresh and quarterly aggregation builder.
- `schema.sql` and `wdi_countries.sql` — PostgreSQL design and country seed for a future hosted database.

A `.sqlite.gz` or `.csv.gz` file is compressed data. GitHub's text preview will look like garbled characters; download and extract it before opening. For a quick phone-friendly view, open `macro_research_latest.csv` in a spreadsheet app. The single-file `macro_research_all_observations.csv.gz` has all history and can be extracted and imported into a spreadsheet. To query the complete relational database, join and extract the SQLite parts, then open the result with a SQLite app.

## What is included

### Annual indicators

World Bank World Development Indicators (WDI): nominal and real GDP in US dollars and local currency; nominal and real GDP per capita; reported real GDP and real GDP-per-capita growth; PPP GNI per capita; life expectancy; ILO-modelled unemployment; $3.00/day poverty at 2021 PPP; CPI index and inflation; and population. Two additional annual nominal-growth series are calculated from current-local-currency GDP and GDP per capita to avoid exchange-rate changes driving nominal growth comparisons.

### Quarterly indicators

IMF quarterly national accounts provide nominal and real GDP in domestic currency, both seasonally adjusted and not seasonally adjusted. The database also includes GDP per capita and growth rates. Quarterly per-capita levels are **estimates**: quarterly GDP is divided by a linearly interpolated annual World Bank population series. They are not official quarterly per-capita releases.

IMF monthly CPI and producer-price index (PPI) inputs are averaged across all three months of a quarter; incomplete quarters are omitted. Quarterly CPI inflation is calculated as the year-over-year change in the quarterly mean CPI. The IMF policy/central-bank rate uses the last reported monthly value in each quarter. Monthly inputs are not retained in the database.

India's WPI is a separate series from PPI. The current India WPI series uses the Government of India's 2022-23 base, all-commodities row, and quarterly averages. It currently has 13 observations from 2023-Q2 through 2026-Q2. It is intentionally India-only; no other country's WPI is filled using PPI.

### Coverage and missing data

Coverage differs substantially across indicators. WDI GDP series have up to roughly 213-217 economies; WDI life expectancy currently ends in 2024; unemployment has 187 economies; and poverty observations are survey-based and irregular rather than a value for every country and year. Among quarterly series, CPI has 186 economies, policy rates 82, PPI 73, and quarterly GDP availability ranges from 66 to 109 economies depending on adjustment and series. India WPI has one economy. The exact current economy counts and period spans are in the `indicator_coverage` view.

Missing values are omitted, never replaced with zero. Annual poverty rows retain survey years. Quarterly CPI/PPI/WPI means require a full three-month quarter. Seasonal adjustment is retained with quarterly GDP. Growth fields distinguish year-over-year changes from non-annualized, seasonally adjusted quarter-over-quarter changes. Source observations, estimates, derived values, raw values, source-series identifiers, and source metadata are kept distinguishable.

## Open and query the snapshot

From the repository root, download all three SQLite parts, join them in order, and extract the resulting archive. With command-line tools:

```sh
cat database/macro_research.sqlite.gz.part00 database/macro_research.sqlite.gz.part01 database/macro_research.sqlite.gz.part02 > database/macro_research.sqlite.gz
gzip -dk database/macro_research.sqlite.gz
sqlite3 database/macro_research.sqlite
```

For the full-history spreadsheet export, download and extract `database/macro_research_all_observations.csv.gz`.

Example: India's quarterly real GDP growth, year over year:

```sql
SELECT c.country_name, o.period, o.value, o.value_status, o.seasonal_adjustment
FROM observations AS o
JOIN countries AS c ON c.wb_code = o.country_code
WHERE o.country_code = 'IND'
  AND o.indicator_code = 'gdp_real_growth_yoy_pct_quarterly'
ORDER BY o.period;
```

See indicator descriptions and coverage before comparing series:

```sql
SELECT * FROM indicator_coverage ORDER BY frequency, indicator_code;
SELECT indicator_code, display_name, frequency, unit, definition, availability
FROM indicators ORDER BY frequency, indicator_code;
```

The SQLite snapshot includes `countries`, `sources`, `indicators`, `source_snapshots`, `source_series_metadata`, and `observations` tables, plus `indicator_coverage` and `research_observations` views.

## Refresh

Python 3's standard library is sufficient; an internet connection is required. A full refresh fetches annual WDI plus quarterly IMF data and India WPI, aggregates monthly inputs, validates the SQLite file, and then writes the compressed database, latest-values CSV, and full-history CSV export. The SQLite database and each export are written through temporary files before replacement.

```sh
python3 database/scripts/refresh_macro_database.py --output database/macro_research.sqlite
```

For a smaller annual-only snapshot, run:

```sh
python3 database/scripts/refresh_macro_database.py --annual-only --output database/macro_research.sqlite
```

The `--annual-only` option intentionally leaves the quarterly series empty; do not use it to refresh the shared full release.

The IMF subscription-key environment variable is supported if the API requires one in a future refresh; never commit credentials. The script records retrieval URLs and row counts in `source_snapshots` and source dimensions in `source_series_metadata`.

## Health audit and database readback tests

Run the audit from the repository root after downloading/cloning the repository:

```sh
python3 database/scripts/health_check.py --root database --compact
```

The audit assembles the three SQLite archive parts in a temporary folder, opens the resulting database read-only, and removes the temporary copy when finished. To audit an already extracted SQLite file instead:

```sh
python3 database/scripts/health_check.py --database database/macro_research.sqlite --root database --compact --json health-report.json
```

The report scores explicit checks across SQLite integrity, schema, data validity, relationships, indicator coverage, real readback queries, CSV parity, query plans, and storage. It checks retrieval by country and indicator, chronological histories, joined descriptive records, latest values, and ranked results. JSON output includes every check, coverage spans, database/page sizes, query plans, and median timings. Timings are descriptive because hardware varies; they are not treated as a universal pass/fail speed limit. The percentage summarizes checks passed, not the probability that the data are correct. Critical corruption or missing core data caps the overall score.

The audit is offline and uses Python's standard library. It does not change the source database or contact providers. CSV parity is checked when `--root` is supplied. Exit status is 0 when no checks fail, 1 for non-critical failures, and 2 for critical failures or an audit that cannot run.

Run the audit module's self-tests (they use temporary sample databases and deliberately introduce known faults):

```sh
python3 -m unittest discover -s database/tests -v
```

## Sources and attribution

- World Bank, [World Development Indicators](https://datacatalog.worldbank.org/search/dataset/0037712/world-development-indicators), accessed through the [Indicators API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392). WDI is licensed under CC BY 4.0. Credit the World Bank, cite indicator codes, and note that this release contains calculated and aggregated values.
- International Monetary Fund, [National Economic Accounts, Quarterly Data (QNEA)](https://data.imf.org/Datasets/QNEA), and IMF CPI, Monetary and Financial Statistics interest-rate, and PPI data. Cite the relevant IMF dataset and follow the [IMF statistical-data usage terms](https://www.imf.org/en/about/copyright-and-terms).
- Government of India, Office of the Economic Adviser, [WPI and PPI index files](https://eaindustry.nic.in/download_data_2223.asp), WPI base 2022-23. The publisher identifies the latest two monthly WPI figures as provisional. Attribution and source metadata are retained; consult the publisher's reuse terms before redistributing the WPI series.

The current WPI values in this snapshot are quarterly averages through 2026-Q2. They do not include the currently provisional July and August 2026 monthly values.

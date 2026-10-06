# Macroeconomic research indicators

This is the Society's first curated reference dataset. It combines annual World Bank indicators with selected quarterly IMF series and India's Office of the Economic Adviser WPI. The **reviewable CSV files and SQLite schema are the canonical release source**; the SQLite database is reproducibly built locally and is not committed as a binary artifact.

## Quick start

From the repository root, build and test the release:

```sh
python3 datasets/macroeconomic-indicators/scripts/health_check.py \
  --source-root datasets/macroeconomic-indicators/source --compact
python3 -m unittest discover -s datasets/macroeconomic-indicators/tests -v
python3 datasets/macroeconomic-indicators/scripts/build_database.py
```

The builder writes `datasets/macroeconomic-indicators/macro_research.sqlite` locally. Open it with SQLite or query it in Python, R, or another SQLite-compatible tool. The built database is ignored by Git; the files needed to reproduce it are versioned.

To produce a detailed health report, add `--json health-report.json` to the audit command. The report tests source-file checksums and row counts, schema, SQLite integrity, foreign keys, data constraints, all series partitions, representative readback queries, and query plans. Timing measurements are informational and machine-dependent.

## Reviewable release structure

```text
datasets/macroeconomic-indicators/
  README.md                 study guide, methods, caveats, citation
  metadata.yml              dataset-level catalogue metadata
  CHANGELOG.md              release history
  schema/sqlite.sql         readable SQLite DDL, indexes, and views
  source/                   canonical UTF-8 CSV input release
    countries.csv           geography reference table
    indicators.csv          indicator codebook and definitions
    sources.csv             publishers, terms, and attribution
    source_snapshots.csv    retrieval provenance
    source_series_metadata.csv
    schema_meta.csv         release policies and provenance notes
    observations/{annual,quarterly}/<indicator_code>.csv
    release.json            per-file SHA-256 and row-count manifest
  scripts/                  build, prepare, refresh, and health-check tools
  tests/                    isolated tests, including known-fault cases
```

Each observation partition contains one indicator's annual or quarterly rows, ordered by country, period, and source-series code. This makes review focused: for example, a change to an indicator can be inspected without opening or diffing a binary snapshot. `\N` represents SQL NULL; literal strings beginning with a backslash are escaped by doubling the leading slash.

## Refresh and publish workflow

1. Refresh upstream data into a temporary candidate SQLite file (this step needs internet):

   ```sh
   python3 datasets/macroeconomic-indicators/scripts/refresh_macro_database.py \
     --output /tmp/macro_research_candidate.sqlite
   ```

2. Export the candidate into reviewable source files, rebuild it from those files, and compare the rebuilt database to the candidate:

   ```sh
   python3 datasets/macroeconomic-indicators/scripts/prepare_source_data.py \
     --database /tmp/macro_research_candidate.sqlite \
     --output datasets/macroeconomic-indicators/source
   python3 datasets/macroeconomic-indicators/scripts/build_database.py \
     --verify-against /tmp/macro_research_candidate.sqlite
   python3 datasets/macroeconomic-indicators/scripts/health_check.py \
     --source-root datasets/macroeconomic-indicators/source --compact
   python3 -m unittest discover -s datasets/macroeconomic-indicators/tests -v
   ```

3. Review the CSV diffs, source notes, health report, and test results in a pull request. Publish only after another Society reviewer has checked attribution, terms, methods, and data quality. Add a dated changelog entry and tag a release.

## What is in this release

- 217 World Bank country/economy entries, 40 indicators, and 263,863 observations (96,475 annual and 167,388 quarterly).
- Annual and quarterly series only. Monthly IMF and India OEA inputs are aggregated where documented; monthly values are not retained.
- The country table follows the World Bank's economies catalogue and includes territories as well as sovereign states. Join by `wb_code`; `serial_no` is not a ranking or permanent identifier.
- Quarterly GDP per-capita series are estimates based on annual population interpolation. Missing values are not filled with zero. See indicator definitions and coverage for series-specific caveats.

The SQLite database contains `countries`, `sources`, `indicators`, `source_snapshots`, `source_series_metadata`, `observations`, and `schema_meta`, plus `indicator_coverage` and `research_observations` views.

## Example research query

```sql
SELECT country_name, period, value, value_status, seasonal_adjustment
FROM research_observations
WHERE wb_code = 'IND'
  AND indicator_code = 'gdp_real_growth_yoy_pct_quarterly'
ORDER BY period;
```

## Sources and attribution

- World Bank, [World Development Indicators](https://datacatalog.worldbank.org/search/dataset/0037712/world-development-indicators), accessed through the [Indicators API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392). WDI is licensed under CC BY 4.0; credit the World Bank and cite indicator codes.
- IMF, [Quarterly National Accounts](https://data.imf.org/Datasets/QNEA), CPI, Monetary and Financial Statistics interest rates, and PPI. Follow the [IMF terms](https://www.imf.org/en/about/copyright-and-terms).
- Government of India, Office of the Economic Adviser, [WPI/PPI series](https://eaindustry.nic.in/download_data_2223.asp), WPI base 2022-23. Review publisher reuse terms before redistribution.

See the source tables and indicator definitions for exact retrieval records, series identifiers, transformations, release coverage, and notes. Cite this dataset as: *Pondicherry University Economics Society, Macroeconomic Research Indicators, release 2026-09-29*, together with the relevant upstream sources. A DOI-backed archival deposit is recommended when institutional access is available; GitHub is the working and review home, not a permanent scholarly archive.

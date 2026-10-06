# Reviewable source data

This directory is the version-controlled source release for the macroeconomic SQLite database. CSV files are plain UTF-8 with a header row and `\N` for SQL NULL. Each observation file contains one indicator only, so a change can be reviewed without diffing a binary database or a monolithic compressed export.

## Layout

- `countries.csv`, `sources.csv`, `indicators.csv`, `source_snapshots.csv`, `source_series_metadata.csv`, and `schema_meta.csv` are reference/provenance tables.
- `observations/annual/<indicator_code>.csv` and `observations/quarterly/<indicator_code>.csv` contain smaller indicator series. If an indicator is large, it is split into five-year files such as `<indicator_code>_2000_2004.csv`; each partition is limited to about 1.5 MB so it remains practical to inspect and review.
- `release.json` records the row count and SHA-256 checksum for every CSV. The builder refuses incomplete, changed, or unexpected files.

The SQL table and column definitions are in `database/schema/sqlite.sql`. Use the repository guide for indicator meaning, transformations, caveats, source attribution, and the current release citation.

To rebuild the SQLite deliverable, run `python3 database/scripts/build_database.py`. To audit source files, database integrity, retrieval queries, coverage, and index plans, run `python3 database/scripts/health_check.py --source-root database/source --compact`.

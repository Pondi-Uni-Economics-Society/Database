# Macroeconomic Research Data

This repository contains a documented macroeconomic data snapshot prepared for research and learning by the Economics Society, Department of Economics, Pondicherry University.

The current release combines annual World Bank indicators with selected quarterly series from the IMF and India's Office of the Economic Adviser. It includes the SQLite snapshot, CSV exports, database schema files and the script used to refresh and rebuild the data.

## Start here

- Read the [database guide](database/README.md) for coverage, definitions, sources, caveats, and ways to query or refresh the data.
- Open [`database/macro_research_latest.csv`](database/macro_research_latest.csv) for a compact latest-values view.
- Use [`database/macro_research_all_observations.csv.gz`](database/macro_research_all_observations.csv.gz) for the full observation export.
- Use the split SQLite snapshot in `database/` for relational queries. The guide explains how to join and extract its parts.

## Refresh the snapshot

From the repository root, run:

```sh
python3 database/scripts/refresh_macro_database.py --output database/macro_research.sqlite
```

The script requires Python 3 and an internet connection. Review the source notes, attribution, frequency rules and estimates in the [database guide](database/README.md) before using or redistributing the data.

## About this repository

This repository is for macroeconomic data and its reproducible preparation. Society events, the annual magazine and other work can be maintained separately as those projects become active.
# Economics Society research data

This repository is a reviewed collection of research datasets maintained by the Economics Society, Department of Economics, Pondicherry University. Each dataset has its own documentation, sources, methods, quality checks, and release history.

## Start here

- Browse the [dataset catalogue](datasets/README.md) and its [deposit and review process](governance/DEPOSIT_REVIEW_CHECKLIST.md).
- Read the [macroeconomic indicators guide](datasets/macroeconomic-indicators/README.md), the first dataset in the collection.
- The macro dataset's human-reviewable source is partitioned UTF-8 CSV, with a readable SQLite schema. Build a local SQLite database by running `python3 datasets/macroeconomic-indicators/scripts/build_database.py`.
- Validate the source files and database with `python3 datasets/macroeconomic-indicators/scripts/health_check.py --source-root datasets/macroeconomic-indicators/source --compact`.

Do not submit confidential, personal, restricted, or otherwise non-shareable data to this public repository. See the [deposit template](templates/dataset-deposit/README.template.md) before proposing a new dataset.

# Society research data catalogue

This repository is a curated collection of research datasets—not a single table that combines unrelated projects. Each dataset has its own guide, metadata, sources, files, methods, tests, and release history. Dataset maintainers should preserve the original source and document all transformations.

## Published datasets

| Dataset | Contents | Status |
|---|---|---|
| [Macroeconomic indicators](macroeconomic-indicators/README.md) | Reviewed annual and quarterly country-level indicators with source-level provenance | Published; release 2026-09-29 |

## Deposit and review process

1. Start from `../templates/dataset-deposit/` and open a draft pull request. Do not upload confidential, personal, licensed-restricted, or otherwise non-shareable data to this public repository.
2. Include the study guide, metadata, variable/data dictionary, source/rights information, and reproducibility scripts. Use open, documented file formats where possible.
3. A Society data reviewer checks completeness, permissions/privacy, documentation, integrity, and reproducibility. A faculty adviser or delegated review group should approve releases until formal roles are established.
4. Accepted datasets are moved under a stable dataset ID in this catalogue. Add a release entry and changelog; do not silently replace a published release.
5. Make a GitHub release for the versioned files. For a formal scholarly DOI and long-term preservation, deposit the approved release in an institutional or trusted repository such as Dataverse/Zenodo when available; Git history is not a substitute for an archival DOI.

Use `../governance/DEPOSIT_REVIEW_CHECKLIST.md` for the review. Every data contributor remains responsible for permissions, participant consent, disclosure risk, and accurate source attribution.

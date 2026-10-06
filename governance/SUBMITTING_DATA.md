# How to submit a research dataset

This repository is public. A pull request is a proposal for review, not permission to publish sensitive or restricted data. If you are unsure whether a file may be shared, do not upload it; ask the faculty adviser or data reviewer first.

## Before preparing files

1. Confirm who created or owns each file and that the Society may redistribute it publicly. Record the source, license or terms, attribution, and access date. A file being downloadable online does not automatically mean it may be republished.
2. Check for personal or confidential information, including names, contact details, student IDs, exact locations, free-text responses, and combinations that could identify people. Do not put restricted data in this public repository, even temporarily in a pull request.
3. Pick a short, stable dataset ID in lowercase kebab-case, for example `rural-credit-survey-2026`. Ask a maintainer before reusing an existing ID.

## Prepare the submission

Copy `templates/dataset-deposit/` into a new folder under `datasets/<dataset-id>/`. Replace the template fields and include:

- `README.md`: purpose, coverage, unit of observation, file descriptions, sources/rights, methods, limitations, quality checks, and version history.
- `metadata.yml`: dataset catalogue details, license/access status, release version/date, and reproduction instructions.
- `codebook.csv`: one row per variable, with definition, unit, categories/codes, missing-value meaning, and construction notes.
- The shareable data files, using open, clearly named formats such as CSV where practical.
- Reproduction scripts and tests if the data were cleaned, merged, transformed, or derived. Explain the software and exact steps needed to rerun them.

Example layout:

```text
datasets/<dataset-id>/
  README.md
  metadata.yml
  codebook.csv
  data/
    observations.csv
  scripts/
    prepare_data.py
  tests/
    test_release.py
```

Keep original values distinguishable from derived values. Do not encode missing data as zero unless zero is genuinely the observed value; document missing-value codes and units. If a file is large, partition it along meaningful units such as year, geography, or indicator—not into arbitrary byte chunks. Include a manifest with file sizes, row counts, and SHA-256 checksums for multi-file releases.

## Open a pull request

1. Create a branch and add the proposed dataset folder. Avoid changing unrelated datasets.
2. Run the included preparation and validation steps. Check that files open, headers and types are understandable, keys and duplicates are reviewed, missingness and ranges are summarized, and all scripts/tests can be rerun.
3. Open a draft pull request titled `Dataset proposal: <dataset title>`. In its description, summarize the data, sources and rights, changes made, checks run, and any unresolved questions. Do not attach confidential data to the PR.
4. Ask a Society data reviewer to use the [review checklist](DEPOSIT_REVIEW_CHECKLIST.md). A faculty adviser or delegated review group should approve releases until formal roles are established. Respond to questions and update the PR as needed.
5. Do not describe the dataset as accepted or published until the review is approved and the maintainer merges it. The maintainer then updates the catalogue and changelog, tags a version, and considers a DOI-backed archival deposit.

## Important

The Society does not yet promise secure storage, access control, long-term preservation, or expert disclosure-risk review. This public GitHub repository is only for data cleared for public redistribution. Contributors remain responsible for obtaining permissions and accurately describing sources and methods.

# Research-data deposit review checklist

Use this checklist before accepting a dataset into the public Society repository. Mark each item pass, not applicable, or needs follow-up; record reviewer and date in the pull request. A pull request is not approval to publish. If sharing rights, consent, privacy, or disclosure risk are uncertain, stop review and do not merge until resolved. Never place restricted data in a public branch or pull request.

## Rights, safety, and access

- [ ] Contributor has authority to share every file; licenses, attribution, and reuse restrictions are recorded.
- [ ] No credentials, direct identifiers, confidential records, or data prohibited by consent, law, agreement, or institutional policy are present.
- [ ] Disclosure/re-identification risk was considered, especially for small geographic groups or sensitive attributes.
- [ ] Public-release status is explicitly confirmed. Restricted data are not stored in this public repository.
- [ ] If participants are involved, consent and applicable institutional/ethics requirements cover this exact public release; uncertainty is escalated before any merge.

## Research documentation

- [ ] Dataset ID, title, authors/affiliations, summary, topics, coverage, unit of observation, and release version are supplied.
- [ ] Each file is described; variable names, meanings, units, categories, missing codes, and derived variables are documented.
- [ ] Sources, retrieval/access dates, methods, transformations, limitations, and citation are clear enough for a secondary researcher.
- [ ] Reproduction instructions/scripts are included where data are cleaned, merged, or derived.

## Technical and quality checks

- [ ] Files open; encoding, headers, types, row counts, and key uniqueness are checked.
- [ ] Contributor's preparation steps can be followed from a clean checkout using the documented software and commands.
- [ ] Missingness, ranges, duplicates, joins, and known data-quality limitations have been reviewed.
- [ ] Automated tests or validation steps pass and can be rerun by another member.
- [ ] File names are descriptive and stable; large files are partitioned meaningfully rather than split into arbitrary chunks.

## Release and review record

- [ ] Change summary, changelog, and version are present; prior released versions are not silently overwritten.
- [ ] Required items pass or have a documented resolution; questions and reviewer decision are recorded in the pull request.
- [ ] Catalogue, version/change history, and release files agree; no unrelated or temporary files are included.
- [ ] Dataset catalogue is updated and an appropriate institutional/archival repository is considered for DOI-backed preservation.

Reviewer:  
Review date:  
Decision: approve / revise / decline  
Notes:

# Data Steward Task Intake Template

Use this template when accepting, scoping, or logging a data stewardship assignment.

## 1. Assignment Scope
- **Objective / Scientific Claim**: [State the specific claim or dataset goal to support]
- **Assigned Project & Workspace**: [Project ID / Workspace ID / Worktree path]
- **Coordinator / Requester**: [e.g., Chief of Staff (`fhti51x1qapqy7grqm3xoref`) or User]
- **Target ETA**: [Estimated completion time / milestone schedule]

## 2. Inputs & Provenance
- **Raw Data Sources**: [File paths, repository URLs, accession numbers, or database tables]
- **Access & License Constraints**: [License, data use agreement, privacy constraints]
- **Versions & Checksums**: [Commit SHA, release tag, MD5/SHA256 hashes]
- **Declared Schema & Dictionaries**: [Expected fields, types, units, identifier schemes, null semantics]

## 3. Desired Outputs
- **Data Artifacts**: [Derived dataset path(s), data dictionary, schema contracts]
- **Reports**: [Data quality report, constraint validation output, lineage diagram]
- **Validation Scripts**: [Polars / pytest validation recipes and commands]

## 4. Acceptance & Verification Checks
- [ ] Raw data immutability verified (checksum match before/after).
- [ ] Schema constraints validated (types, nulls, uniqueness, ranges).
- [ ] Lineage and transformations documented end-to-end.
- [ ] Quality flags cataloged with proposed resolutions.

## 5. Scientific Decisions Requiring User Approval
- **Exclusions / Outliers**: [Observations flagged for exclusion with scientific rationale]
- **Imputation / Missingness**: [Handling of missing records or ambiguous measurements]
- **Unit & Identifier Remapping**: [Conversions or cross-reference mappings affecting interpretation]

## 6. Dependencies & Reviews
- **Research Software Engineer**: [Schema contract integration / pipeline hookup]
- **Statistical Reviewer**: [Methodological review of sampling or distribution assumptions]
- **Independent Reviewer Model**: GPT-6.1 Sol (low effort)

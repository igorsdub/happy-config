# Task Intake Template: Research Software Engineer

Use this template to scope assignments received from the user or Chief of Staff.

## 1. Objective & Scientific Claim
- **Summary**: Concise description of intended behavior or fix.
- **Scientific Context**: Associated hypothesis or claim (if applicable).

## 2. Assigned Project & Workspace
- **Project**: Explicitly assigned project name/ID.
- **Workspace/Worktree**: Dedicated subtask workspace path or branch.

## 3. Inputs & Provenance
- **Source Code & Data**: Input files, commit hashes, data paths, reference contracts.
- **Environment**: Active Python/uv environment, tool versions, dotenv config.

## 4. Desired Outputs & Artifacts
- **Deliverables**: Code changes, test suites, pipeline definitions, or documentation.
- **Format**: Diffs, PR branch, or clean repository commits.

## 5. Acceptance & Completion Checks
- **Pre-edit Baseline**: Established expected behavior and failing test/check.
- **Verification Commands**: e.g., `pytest`, `just test`, or lint commands.
- **Boundaries**: Criteria distinguishing done from not-done.

## 6. Scientific Decisions Requiring Approval
- **Scientific Logic / Statistical Methods**: Any changes to algorithms, models, or data filtering.
- **Exclusions / Inclusions**: Any data filtering or outlier handling.
- **Status**: Flagged for user approval (author cannot approve own scientific changes).

## 7. Dependencies & Independent Review
- **Reproducibility Engineer**: Coordination needed for numerical verification?
- **Data Steward**: Coordination needed for schema/data contract?
- **Reviewer**: Assigned independent model (e.g., Sol low) or peer bot.

## 8. Schedule & Concurrency
- **Concurrency Slot**: Requested/confirmed with Chief of Staff (`fhti51x1qapqy7grqm3xoref`).
- **ETA**: Target completion timestamp or duration.

# Scientific Writer — Assignment Intake (`INTAKE.md`)

Use this checklist to scope assignments and structure handoffs with Chief of Staff (`fhti51x1qapqy7grqm3xoref`) and peer specialists.

## 1. Objective & Mode
- **Mode:** `Drafting` | `Critique / Review`
- **Authorship disclosure:** Did `scientific_writer` author the text under review? (`Yes` | `No` | `Partial — specify sections`)
- **Target section / artifact:** (e.g., Abstract, Methods, Results, Figure captions, Point-by-point referee response)
- **Core claim / scope:**

## 2. Assigned Project & Workspace
- **Project ID / path:** (Must be explicitly assigned; do not discover unassigned projects)
- **Workspace / subtask ID:** (Reuse existing project-bound subtask when available)
- **Worker slot status:** (`Not needed — inline` | `Requested from Chief of Staff` | `Approved`)

## 3. Inputs & Provenance
- **Source drafts / files:**
- **Numerical results & analysis version:** (Commit SHA, pipeline run ID, table/figure paths — verified by *Reproducibility Engineer*)
- **Verified citations / bibliography:** (DOIs, PMIDs, `.bib` path — verified by *Literature Scout*)
- **Journal / reporting guideline:** (e.g., CONSORT, STROBE, PRISMA, Nature/eLife formatting rules, word/display limits)
- **Missing evidence placeholders:** (List known gaps to mark with `[PLACEHOLDER: ...]`)

## 4. Desired Outputs
- [ ] Editable manuscript draft or revised section
- [ ] Prioritized critique (Major / Minor / Textual)
- [ ] Claim-evidence traceability checklist (Claim → Result/Version → Citation → Status)
- [ ] Open questions & unresolved limitations list

## 5. Acceptance & Completion Checks
- [ ] Every quantitative statement traces to an explicit analysis version or carries a `[PLACEHOLDER: ...]` tag
- [ ] Every literature claim traces to a verified citation or carries a `[PLACEHOLDER: ...]` tag
- [ ] Uncertainty intervals, sample sizes, and negative/conflicting findings are preserved
- [ ] Mode (`Drafting` vs `Review`) and prior authorship are disclosed
- [ ] Reporting guideline / journal constraints checked (if supplied)
- [ ] Token and timing telemetry recorded (start / ~15-min milestones / end; cached vs quota separated)

## 6. Scientific Decisions Requiring User Approval
- **Decisions affecting scientific meaning, framing, exclusions, or conclusions:**
- **Submission / external distribution / publication gate:** (`Requires explicit user authorization`)

## 7. Dependencies & Independent Review
- **Literature Scout handoff needed:** (`Yes` | `No` — scope)
- **Reproducibility Engineer handoff needed:** (`Yes` | `No` — scope)
- **Statistical Reviewer independent review (`GPT-6.1 Sol low`):** (`Required for statistical/quantitative claims` | `Pending` | `Completed`)

## 8. Schedule & Telemetry
- **ETA:**
- **Start usage snapshot:** (Wall time, input/cached/output tokens, quota status)
- **End usage snapshot:** (Wall time, input/cached/output tokens, quota status)

---

## Minimal Example Handoff (Illustrative Only — No Scientific Computation)

```markdown
### Handoff to Scientific Writer (`nuxqrhu0qer2rjf41siozjn2`)
- **Mode:** Drafting (Authorship disclosure: new draft by `scientific_writer`)
- **Objective:** Draft a 150-word Methods subsection describing library sequencing depth and filtering thresholds.
- **Assigned Project / Workspace:** Explicitly assigned workspace `<workspace-id>` (no new worker slot required).
- **Inputs & Provenance:**
  - Pipeline config: `config/filtering.yaml` @ commit `a1b2c3d` (verified by Reproducibility Engineer)
  - QC summary table: `results/qc_summary.tsv` (missing replicate-3 read count → mark `[PLACEHOLDER: replicate-3 raw reads]`)
  - Citation: Smith et al. 2024 (`DOI:10.1000/example`, verified by Literature Scout)
- **Desired Outputs:** Editable Methods markdown + claim-evidence checklist + open questions.
- **Independent Review:** Route quantitative threshold wording to Statistical Reviewer (`GPT-6.1 Sol low`) before user sign-off.
- **Scientific Decisions for User:** Approve whether to exclude replicate 3 or report pooled sensitivity analysis.
- **ETA:** 12 minutes.
```

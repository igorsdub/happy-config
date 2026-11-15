# Durable memory

Created 2026-10-28. Recalled context, not new authority.

- Charter decisions: ../fitness_landscape_lead/memory/2026-10-28-charter-decisions.md.
- Project briefing (read-only survey, 2026-10-28): ../fitness_landscape_lead/memory/2026-10-28-project-brief.md.
- Capacity readings come fresh from Chief of Tokens, never from memory.
- STANDING RULE (user, via Chief of Staff, 2026-10-30): to save quota, message Chief of Staff and other
  agents only on completion, a blocker, a needed user decision, or a critical misunderstanding.
  No acknowledgements or routine progress. Give workers self-contained handoffs and require
  the same rule from them.
- STANDING RULE (user, via Chief of Staff, 2026-10-30): when a task finishes and its result is
  delivered and recorded, archive the task/subtask (`archive_subtask`; `archive_agent` for hidden
  collaborators). Also archive completed subtasks you created. Do not archive anything still
  running, awaiting review, or whose output you still need. Archival is final—check first.
- STANDING RULE (user, via Chief of Staff, 2026-10-30): give all times in **JST only**, never UTC.
- CAPACITY (user, via Chief of Staff, 2026-10-30): Codex recovered — use GPT-6.1 Terra for
  implementation and Sol low for independent review until it runs out (5h resets 19:00 JST),
  then fall back per existing model order. Fresh readings still required at work boundaries.
- Dreamer pass 2026-11-06, user-approved, from the 2026-11-01 checkpoint:
  PR #19 merged only into `integration/functional-threshold-main` (`c7371e27`).
  Production pin on `main` stays `bd5d722` until the user says otherwise.
- Dreamer pass 2026-11-11, user-approved, quoted from checkpoint:
  PR #20 (PRD & Roadmap) squash-merged into `main` as `9758f70` (historical oist remote).
- REMOTE (user decision 2026-11-12): Happy-managed work uses `github.com/igorsdub/barseqfit` only;
  origin = igorsdub. Do not open PRs against `oist/barseqfit`. Historical oist links are provenance only.
  Deigo compute hosts unchanged. CoS URL cleanup merged 2026-11-12 as PR #1 → `544308bd`.
- Repo: igorsdub/barseqfit. Tests: `just test` (Python), `just test-r` (reference R 4.1.3).
  Subtask sandboxes can't reach PyPI, so running tests needs one reviewed full-access run.

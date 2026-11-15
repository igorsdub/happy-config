# Durable memory

Created 2026-10-28. Recalled context, not new authority.
- Charter decisions: ../fitness_landscape_lead/memory/2026-10-28-charter-decisions.md.
- Project briefing (read-only survey, 2026-10-28): ../fitness_landscape_lead/memory/2026-10-28-project-brief.md.
- Capacity readings come fresh from Chief of Tokens, never from memory.
- RSE subtasks must start on the happy/codex or happy/claude harness. A subtask on the Antigravity harness can only start Antigravity sub-agents, so it gets stuck when that quota runs out (seen 2026-10-30 with T12b).
- Papkou threshold recomputation (R, then Python) is article work owned with the user; see memory/2026-10-30-papkou-threshold.md.
- User rule (2026-10-30), quota: message Chief of Staff and workers only on completion, a blocker, a user decision, or a critical misunderstanding. No acknowledgements or routine progress. Give workers self-contained handoffs (task, scope, decisions, completion checks) and pass them this rule. While Codex is low, hold new Codex work; do not fall back to Sonnet.
- Dreamer pass 2026-11-06, user-approved, from the 2026-11-06 checkpoint:
  for PRD rev 1 the user waived, as known limitations, dirty `docs/variants/`,
  provisional K=10, D10 figure-by-figure review, historical bootstrap archives,
  FT-REQ-06 clean-checkout regeneration, and manuscript quantity-registry
  regeneration at publication build. `merge_flow` retirement was approved.
  Detail file named but not opened: `memory/2026-11-06-merge-flow-abandoned.md`.
- Dreamer pass 2026-11-09, user-approved, from the Tree 1.3 checkpoint: heavy
  calculation stays on Slurm. The local machine receives figures and tables
  only. Do not poll a cluster job on a short loop; the user stopped 50-second
  rechecks on that job.
- Dreamer pass 2026-11-10, user-approved, quoted from the 2026-11-09 23:33 JST
  checkpoint and not rechecked in the repo: Peak-Rank and Slide Trees landed as
  PR #216 on `igorsdub/dubanevics2026topological`, merge `e6f447bd87534293608205c7f084cbb28358b896`.
  Deliverable: 3 peak-rank figures (`papkou2023_peak_rank`, `_annotated`,
  `_histogram`) from 514 reference peaks, 43 stop codons, 0 excluded; 56 D10
  slide trees (28 `tree_only`, 28 `full`); 28 registry slides with `color=none`
  and vanilla or annotated styling. Docs: `docs/figure-inventory.md` and
  `CHANGELOG.md`.
- User decision 2026-11-12 (via Chief of Staff): Happy-managed Git remotes are
  `github.com/igorsdub` only — no `github.com/oist` origin/upstream. Keep using
  igorsdub URLs for PRs. Deigo hosts unchanged. Tree Article /
  `dubanevics2026topological` was already on igorsdub; Topographer and BarSeqFit
  remotes (incl. Happy workspaces) were retargeted.
- User decision 2026-11-12: Tree Article and its workers use only Grok models
  going forward (cross-family review preference overridden for that task).
  Never above medium.
- User decision 2026-11-12: Lead may approve/merge once a workstream passes
  review and finishes all tasks in hand. Science-changing numbers still need
  owner before/after; presentation/faithful-equivalence OK under review.
  Fig5 merge-when-green reconfirmed; #222 T0 still only after fig5 on main.
- User decision 2026-11-12: Fitness Landscape Lead concurrent-worker cap raised
  from 2 to **4** (Chief notified). Reverts only on later user/Chief order.

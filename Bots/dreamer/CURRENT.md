# CURRENT (Dreamer)

## Goal
Offline memory consolidation across completed tasks and bot sessions.

## Status
- 2026-11-09 proposal approved by the user and applied.
- Live `MEMORY.md` updated for Fitness Atlas Lead and Fitness Landscape Lead.
- `AGENTS.md` and policy files not touched.

## Decisions
- Proposal-only until the user approves. This pass was approved.
- Quota, wake ids, Slurm ids, and the own-chat approval rule were not copied.

## Constraints
- Max 16 KiB.
- Never edit live memory or policy unless the user approves that write.

## Artifacts
- `Memory/proposals/2026-11-09-consolidation.md` (marked applied)
- Writes: `fitness_atlas_lead/MEMORY.md`, `fitness_landscape_lead/MEMORY.md`

## Verification
- Both ADD bullets from the approved proposal are in those files.

## Open issues
- Scientific numbers and paths are still checkpoint quotes.
- Dreamer is not in the checkpoint-seal bot registry, so the official seal command fails.

## Next action
Idle until the next consolidation.

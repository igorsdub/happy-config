# Current state (Chief of Tokens)

## Goal
Keep this file as Chief of Tokens's short-term memory so its chat can be compacted safely.

## Status
Initial checkpoint created 2026-11-01 by the Bot compaction policy task. No work state recorded yet; the bot replaces this at its next turn end.

## Decisions
Bot model and compaction rules come from the bot lines in Config/AGENTS.md.

## Constraints
Keep under 16 KiB. Keep all eight sections. Never store secrets.

## Artifacts
None recorded yet.

## Verification
Seal with the checkpoint-seal command in this bot's AGENTS.md.

## Open issues
None recorded yet.

## Next action
At the end of the next turn, rewrite this file from the live state and seal it.

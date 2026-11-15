# Current state (Scientific Writer)

## Goal
Await scoped scientific drafting or review assignments from the user or Chief of Staff (`fhti51x1qapqy7grqm3xoref`), maintaining bot short-term memory and context hygiene.

## Status
Idle. Role setup is complete with `AGENTS.md` and `INTAKE.md` verified. Model switch to `antigravity/gemini-3.8-flash` confirmed to Chief of Staff.

## Decisions
- Model is `antigravity/gemini-3.8-flash` at low effort following the persistent bot model policy.
- Bot remains idle without discovering local projects until an explicit project and workspace assignment is received.

## Constraints
- Max 16 KiB size limit. Keep all eight required headings.
- Never store secrets. Preserve claim-evidence traceability and uncertainty intervals.

## Artifacts
- `/Users/igorsdubanevics/Happy/Bots/scientific_writer/AGENTS.md`
- `/Users/igorsdubanevics/Happy/Bots/scientific_writer/INTAKE.md`

## Verification
- MCP `send_agent_message` confirmation delivered to Chief of Staff (`fhti51x1qapqy7grqm3xoref`).
- Seal via `context_maintenance.py --bot scientific_writer checkpoint-seal`.

## Open issues
None. Awaiting task assignment.

## Next action
Remain idle awaiting scoped assignments from the user or coordinator.

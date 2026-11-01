# Context maintenance

Read this when sealing a bot checkpoint, running or scheduling `tools/context_maintenance.py`, or diagnosing a skipped or pending compaction. The tool asks the daemon for its native compaction of a registered bot when every gate passes. It never sends, aborts, archives, resets, or changes mode; a code-level request allowlist enforces this (GET config/bootstrap/messages, POST `compact`, allowlisted targets only).

Scope: sampled, idle-only enforcement, run once per cycle by the caller. It does not change the daemon's own global auto-compaction window.

## Cycle

1. Update the bot's own `CURRENT.md` (its registered checkpoint). Required nonempty sections, as headings: Goal, Status, Decisions, Constraints, Artifacts, Verification, Open issues, Next action. Max 16 KiB. Placeholders (`TBD`, `TODO`, `...`) are rejected.
2. Seal: `python3 ~/Happy/Bots/chief_of_staff/tools/context_maintenance.py --bot <name> checkpoint-seal`. Run it as the last tool call before the final reply; no `CURRENT.md` edit may follow. Done when it prints `"action": "sealed"`. This writes `<bot>/.context/checkpoint-seal.json` (path, sha256, size, time). It never contacts the daemon, never writes a summary and never stores message text.
3. Maintain: `python3 tools/context_maintenance.py --bot <name> maintain` (selectors such as `--bot` or `--all` go before the command). Done when it prints one of the actions below. Do not loop or poll; run it again next cycle.
4. Inspect without side effects at any time: `python3 tools/context_maintenance.py --bot <name> inspect`.

Exit code: 0 for ok outcomes (including skips), 1 for fail-closed anomalies, 2 for usage or allowlist errors.

## What `maintain` does, in order

1. Takes a per-target `flock`; if held, skips.
2. If an attempt is pending, reads recent history once and reconciles it. A `running` compaction stays pending; `completed` or `failed` is recorded and clears it. No new compaction while one is pending.
3. Reads the bot's newest message id. Skips quietly on first sighting or when it is the last compaction's own message; skips (counted) when it differs from the id seen on the previous cycle. Then verifies the bot's local seal: same target and path, `CURRENT.md` still valid, digest unchanged.
4. Takes a fresh `GET /v0/agents/:id/bootstrap` and requires: status `idle`, not archived, no pending question, `wait` null, empty `pending` queue, zero running child agents and background processes and a positive integer context-token count (approximate counts are accepted). `archivedAt`, `pendingQuestionId`, `wait`, the `subagents` and `processes` counts (nonnegative non-bool integers) and the complete `subagents` and `processes` lists must be present and well formed; a missing or malformed field or entry blocks (fail closed).
5. For Chief of Staff only (or with an explicit `--dispatch-db`), blocks if `.context/dispatch.db` has jobs in reserved, sending, running or cancel_pending. An explicit unreadable ledger path blocks.
6. Cooldown (default 30 min, `--cooldown`) after any attempt; a compaction is not repeated until the bot has new activity.
7. Trigger: none by size. Cadence only (every 30 minutes, no token threshold). Freshness: the runner records each bot's newest message id per cycle and compacts only when it is unchanged since the previous cycle; the first sighting never compacts, and nothing is compacted again until there is new activity after a compaction.
8. Persists the attempt intent to `.context/context-maintenance-state-<agent id>.json` (one file per bot) **before** `POST /v0/agents/:id/compact`.

## Actions

| Action | Meaning |
| --- | --- |
| `skip` | A gate failed; `reasons` lists them. Nothing was sent. |
| `compact_requested` | HTTP 202. The compaction message exists in status `running`. This is acceptance, not completion. |
| `pending_running` | Reconciled: the daemon shows the compaction still running. |
| `pending_unknown` | Outcome unknown (lost response, 5xx, no matching message). Never retried automatically. |
| `rejected` | Definite 400/401/403/404. Recorded with cooldown. |
| `error_fail_closed` | An API read failed or was malformed. |

HTTP 409 (agent busy or compaction already running) is a skip and starts no cooldown.

Completion is observed only as a `compaction` block with status `completed` or `failed` in `GET /messages`, found by its message id. Without a receipt carrying the compaction message id (lost 202), the attempt stays `pending_unknown`: no time or trigger heuristic adopts a message. With a known id, only that exact id matches, and its message must be a single manual `compaction` block with status running, completed or failed; anything else stays unknown. `clear-pending` records `operator_cleared_unverified` and never claims completion.

## Unknown outcome

For `pending_unknown`, check the Chief history, then clear it with evidence: `python3 tools/context_maintenance.py --bot <name> clear-pending --evidence "..."`. The cooldown applies afterward.

## Limits

- The idle snapshot is unguarded: the agent can start work between the read and the POST. The daemon's own idle check is the authority (409).
- No API lists scheduled (`wait_until`/delayed) messages. Only the agent's `wait` field is checked; delayed deliveries are not observable.
- Delegated work is seen through running child agents and the local dispatch ledger. Workers started outside both are invisible.
- Not exercised against a live compaction. `inspect` was run read-only against the real daemon; the token is read in memory and never printed or logged.
- Only bots in `tools/bots.json` and their own `CURRENT.md` are allowed. The CLI has no option to widen the allowlist; adding a bot is a registry change.

## Tests

`uv run --no-project --with pytest python -m pytest -q -p no:cacheprovider tests/test_context_maintenance.py` (fake daemon using the documented response shapes; HTTP framing over a socketpair).

## Multi-bot rollout (user decision 2026-11-01)

- Registry: `tools/bots.json` (13 bots, built from `GET /v0/bots`). Only registered agent IDs and their own `CURRENT.md` paths are allowed.
- Sealing: each bot runs `python3 ~/Happy/Bots/chief_of_staff/tools/context_maintenance.py --bot <name> checkpoint-seal` as its last step after saving `CURRENT.md`. The seal is written to `<bot>/.context/checkpoint-seal.json` and never contacts the daemon. It proves only that the save step ran and that `CURRENT.md` is unchanged since; it does not bind `CURRENT.md` to a conversation head (accepted limitation).
- Runner: Chief of Tokens runs `--bot chief_of_staff --bot literature_scout maintain` (pilot) or `--all maintain` every 30 minutes with reviewed full access. No token threshold; approximate token counts are reported, not gated.
- Skips: a bot that is busy, changed since the previous cycle, unsealed, or in cooldown is skipped. Quiet skips (first sighting, nothing new since compaction) do not count. A finished compaction is returned once as `compaction_completed` (ok) or `compaction_failed` (not ok). Three counted skips in a row add a one-time `report` field; Chief of Tokens forwards it to Chief of Staff.
- Pilot: `chief_of_staff` and `literature_scout` for 24 hours, with one compaction followed to `completed`; then `--all`.
- Accepted risks: Gemini Flash writes every summary and detail is lost over time; a bot can edit memory after sealing; an idle bot is compacted after one unchanged cycle.

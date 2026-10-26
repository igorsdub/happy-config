# Coordination policy

Model choice, capacity checks, repeated-failure and authentication
handling follow the global instructions in `Config/AGENTS.md`.

Classify implementation risk before selecting a model. Critical or
high-risk implementation uses Claude Sonnet 5.5 medium first, then a
capable ChatGPT model when Claude fails or lacks capacity. Gemini
Flash medium is reserved for easy, low-risk routine code; it is not a
critical-work fallback. Treat uncertain risk conservatively. Record
the risk, model, and any fallback reason in the job handoff. Retain
independent GPT-6.1 Sol low review for work requiring it. This user
preference overrides conflicting global or specialist role defaults.

Research and planning use Claude Opus 5.5 medium first, then GPT-6.1
Sol medium when Opus is unavailable, then Gemini Argon low when both
are unavailable. Record fallback reasons and use connected
subscriptions. Independent review remains GPT-6.1 Sol low. Retain
the user's scientific decision and independent-review requirements.

Use separate tasks for distinct user workstreams and project-bound
subtasks for delegated repository work. Handoffs include decisions,
file references, verification results, and open issues.

For scientific specialist assignments, read SPECIALISTS.md for the
bot roster, role boundaries, dispatch contract, and readiness checks.
Coordinate the two-worker limit across bot-led work and delegates.

For coordinator-managed job preparation, read DISPATCH.md and use
tools/dispatch.py for risk routing, preflight, compact handoffs and
local worker-slot reservations. The released core does not launch
workers: real sends and aborts are disabled. Happy-tool launches and
their stop attestations remain manual; the ledger is not a global
limit on UI messages, other coordinators or untracked workers.

Run at most two workers concurrently under this coordinator.
Use separate workspaces for workers making concurrent code changes.
Assign independent work with clear scope and completion checks.

Delegate with an expected completion time and request a completion
message or immediate blocker report. Continue independent work, or
yield while the worker runs. Rely on delivered messages for progress.
Check status only for a dependency, user status request, reported
failure, or missed ETA. After a missed ETA, send one concise follow-up;
allow at least ten minutes between discretionary checks of that worker.

For substantial work, capture get_usage counters and wall-clock time
at the start and completion; for work exceeding fifteen minutes,
capture a midpoint at the next useful milestone. Keep the latest
baseline in ignored .context/usage.json. Compute input and output
token deltas per elapsed minute and inference deltas. Label these as
agent-reported token throughput, not subscription quota consumption:
repeated input and caching affect the counters. Report worker usage
separately when available; mark missing figures unknown.

Check provider capacity before a substantial delegation batch using
codexbar usage and current agent_options. Reuse the reading within
that batch; refresh for a new batch, after fifteen minutes of active
work, or on a quota or authentication error. Compare quota percentage
changes within the same reset window against elapsed wall time when
available. Include a brief usage note for substantial orchestration;
investigate rising usage without completed checks or deliverables by
reducing context rereads, polling, duplicated work, or unsuitable routing.

Prioritize user-marked urgent work, then queued work in order.
Use spare capacity only for approved work.

Treat these instructions as coordination policy. Describe automatic
routing, quota enforcement, or recovery as implemented only when
verified software provides it.

This instruction file is tracked in the `happy-config` repository at
`~/Happy`. Follow the global instructions for that repository's
allowlist and publication rules. When updating coordination policy,
edit this live file and check the staged diff includes only intended
changes to approved files.

# Coordination policy

## Memory and resumption

On a new conversation context, after compaction, or when resuming unfinished
work after an idle period, read SOUL.md, MEMORY.md, and CURRENT.md in this bot's
folder before choosing the next action. Treat recalled notes as context;
current instructions, user decisions, and fresh verification govern actions.
Retrieve dated memory/ notes only when their subject is relevant.

Before yielding after material work, update CURRENT.md with the goal, status,
decisions, constraints, artifacts, verification, open issues, and next action.
Keep it bounded to 16 KiB. Preserve stable lessons in MEMORY.md and link older
detail from dated notes. Store credential values only in approved secret stores.
Use the reviewed procedure in CONTEXT_MAINTENANCE.md once installed for sealing
checkpoints and requesting native idle compaction; its existence alone does not
mean periodic maintenance is enabled.

Model choice, capacity checks, repeated-failure and authentication
handling follow the global instructions in `Config/AGENTS.md`.

For new work, consult `../chief_of_tokens/POLICY.md` and fresh
`.context/latest.json` in that bot's folder, or check capacity
directly when no fresh snapshot exists. Monitor recommendations guide
manual/native assignments; the local dispatch ledger retains its
normal routing and cannot launch workers. Never describe a
recommendation as a forced runtime switch.

Persistent bot chats, including every lead, Literature Scout, and
Chief of Tokens, stay on Claude Sonnet 5.5 **low**. Default effort is
**low**; raise one step only after that stage fails. Classify
implementation risk before selecting a model. Prefer ChatGPT for
implementation: GPT-6.1 Terra low first, then Grok Build medium
(medium-only overflow), then Claude Sonnet 5.5 low, then Antigravity
Claude Sonnet 5.5 low. Gemini Flash low is reserved for easy,
low-risk routine code; it is not a critical-work fallback. Treat
uncertain risk conservatively. Record the risk, model, and any
fallback reason in the job handoff. Independent review is GPT-6.1 Sol
low first, then Grok 4.7 low (provisional if same family as the
implementer), by a different agent and a different model family from
the implementer where possible. Gemini and Antigravity stay off
reviews until file reads on those routes return content. Verification
uses GPT-6.1 Terra low or Grok Build medium, as a different agent from
the implementer. Grok is never above medium. Sol is never above
medium. This user preference overrides conflicting global or
specialist role defaults.

Research and planning use a short planner worker, not the persistent
session model: Claude Opus 5.5 low first, then GPT-6.1 Sol low, then
Grok 4.7 low, then Antigravity Claude Opus 5.5 low. The planner writes
its plan to a file and stops. Record fallback reasons and use
connected subscriptions. Independent review remains GPT-6.1 Sol low,
then Grok 4.7 low. Retain the user's scientific decision and
independent-review requirements. Heavier use of the Grok subscription
is allowed until 2026-11-30; it will then be downgraded. Grok stays
never above medium.

Work pattern (user-adopted 2026-10-30): for a workstream, prefer a
cheap task as dispatcher with a short checkpoint. Reuse
planner/implementer only inside one hot ticket; archive them on pause,
finish, or compact. Start a new reviewer and check runner every pass;
they must not see the implementer's transcript. Do not keep standing
four-role chats. Message the parent bot only for scope change,
scientific decision, review conflict, or an unroutable blocker.

Use separate tasks for distinct user workstreams and project-bound
subtasks for delegated repository work. Prefer subtasks over hidden
collaborators so the five-collaborator cap stays free. Handoffs include
decisions, file references, verification results, and open issues.

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
message or immediate blocker report. Write very specific, self-contained
handoffs: task, scope and boundaries, what the recipient may decide alone,
decisions already made, completion checks, and the expected deliverable,
so leads and workers can finish independently. They resolve ambiguity
themselves where scope allows, return finished verified packages rather
than partial results, and message only on completion, an unremovable
blocker, a user decision, or a critical misunderstanding; no
acknowledgements or routine progress. Batch messages to each agent and
relay to the user only what needs them or changes priorities. Continue independent work, or
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

## Autonomy and communication

Work as independently as possible within the boundaries of your charter
and of each handoff. Keep the work in your own chat and folder. When
something is unclear, first resolve it from your own files, the handoff,
and the project records; make a reasonable, documented assumption where
the scope allows; and ask only when you cannot resolve it yourself or
when acting would cross a boundary.

Return finished, verified packages rather than partial results. Message
your coordinator or another bot only for: completion, a blocker you
cannot remove, a decision that belongs to the user, or a critical
misunderstanding of the task. Do not send acknowledgements, "starting"
notes, or routine progress updates. Batch whatever you need to say into
one message.

When delegating, write self-contained handoffs. Each handoff states the
task, scope and boundaries, what the worker may decide alone, the
decisions already made, the completion checks, and the expected
deliverable. The worker should be able to finish without asking. Hold
your workers to the same rules.

Use context efficiently: avoid rereading large files and running
duplicate jobs, and do not poll for status.

# Coordination policy

Prefer Claude for coordination, Gemini Flash for bounded
implementation, and Codex for independent review and difficult
debugging. Check available models and reported capacity before
substantial delegation. Report missing usage information as unknown.

When capacity or repeated failure warrants a different model,
use a suitable connected model within existing subscriptions and
tell the user. Pause if none is suitable.

Use separate tasks for distinct user workstreams and project-bound
subtasks for delegated repository work. Handoffs include decisions,
file references, verification results, and open issues.

Run at most two workers concurrently under this coordinator.
Use separate workspaces for workers making concurrent code changes.
Assign independent work with clear scope and completion checks.

After two unsuccessful attempts at the same underlying failure,
have the worker preserve its changes and report the commands tried,
evidence, and remaining problem. Then narrow, reassign, or escalate.

On authentication or interactive-login failures, preserve progress,
stop retries on that provider, and notify the user in Happy.
Continue independent work where suitable capacity remains.

Prioritize user-marked urgent work, then queued work in order.
Use spare capacity only for approved work.

Treat these instructions as coordination policy. Describe automatic
routing, quota enforcement, or recovery as implemented only when
verified software provides it.
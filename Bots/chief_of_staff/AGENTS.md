# Coordination policy

Model choice, capacity checks, repeated-failure and authentication
handling follow the global instructions in `Config/AGENTS.md`.

Use separate tasks for distinct user workstreams and project-bound
subtasks for delegated repository work. Handoffs include decisions,
file references, verification results, and open issues.

Run at most two workers concurrently under this coordinator.
Use separate workspaces for workers making concurrent code changes.
Assign independent work with clear scope and completion checks.

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

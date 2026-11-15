# Parallel work uses exclusive path claims, and tasks land autonomously after a gate on the exact SHA

Status: accepted 2026-11-15 (grilling session, Plan Worktrees & Landing).

Each task gets one branch and one worktree at `<repo>/.worktrees/<slug>`, never nested. Work splits by exclusive path claims, recorded in `plan.md` and in a per-project `CLAIMS.md` that the project lead keeps in its own state directory, outside git. `.worktrees/` is ignored through `.git/info/exclude`. Landing pushes `HEAD:main` from the task worktree without force, then fast-forwards the primary checkout only if it is on a clean `main`. Overlapping work, and any work that touches a hot file plus its callers, runs in sequence. At most 2 tasks run in parallel per project, or 4 under a user-invoked deadline. A task lands as soon as a fresh Reviewer PASS and the gate pass on the exact rebased SHA. The orchestrator then merges and pushes without a chat approval, `~/Happy` included. Scope changes, allowlist expansion and public releases still ask the user.

## Considered options

- One shared worktree across parallel tasks: rejected, because the git index contends and dirty state leaks. Inside one task, subtasks share the task worktree but edit only their claimed paths, and only the task orchestrator runs git, one commit at a time.
- Doc Writer after the Reviewer: rejected, because it changes the diff after review. Docs come first, then one fresh Reviewer sees the final diff.
- Optimistic parallelism with merge-time conflict resolution: rejected in favor of exclusive claims.
- Section integration branches: rejected, because they live longer and their bases go stale.
- Targeted tests only: rejected. In task_6, targeted tests passed while the full suite and the figures job were broken on the merged SHA, which cost about 6 hours.

## Consequences

Throughput drops, which is accepted to get almost no conflicts. Stale claims (older than 24 h with no live agent) are reported to the user, never auto-cleared. A task that still fails after the Review rounds cap (two fix rounds plus one scope narrowing) keeps its worktree and branch for debugging. Tracking `docs/` needs an entry in the `.gitignore` allowlist.

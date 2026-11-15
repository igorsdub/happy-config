# Happy workflow

Terms for how bots, tasks and workers split, run and land work across projects.

## Parallel work and landing

**Path claim**:
The set of files a task or subtask exclusively owns while it runs; no other running unit may change them.
_Avoid_: lock (for file ownership), reservation

**Claim ledger**:
The per-project `CLAIMS.md`, kept by the project lead in its own state directory outside git, listing each running task with its branch, path claim and start time.
_Avoid_: lock file, registry

**Hot file**:
A file many parts of the code depend on (config, registry, lockfile, shared interface); changing it widens the path claim to its callers.
_Avoid_: shared file, contract file

**Dependency graph**:
The plan's record of which tasks must land before others may start; pieces that share a file are always connected by an edge.
_Avoid_: ordering, schedule

**Gate**:
The checks that must pass on the exact commit that will land: the full suite (plus end-to-end for hot-file tasks), or a declared check in repos without tests.
_Avoid_: CI, test step

**Land**:
Rebase onto fresh `origin/main`, pass the gate on that exact SHA, push it to `main` without force, then remove the worktree, branch and claim.
_Avoid_: ship, merge (alone)

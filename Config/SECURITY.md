# Persistent bot compaction

Rollout (user decision 2026-11-01): a two-bot pilot (`chief_of_staff`,
`literature_scout`) for 24 hours with one compaction observed to completion,
then all registered bots. The guard has no token threshold; it compacts only
an idle bot with nothing running whose newest message is unchanged since the
previous 30-minute cycle and whose sealed `CURRENT.md` still matches.

The runner is Chief of Tokens, using reviewed full access only for
`context_maintenance.py maintain` (`--bot` during the pilot, then `--all`). The guard may use GET bootstrap,
messages and config, and POST compact for registered bots only. Read the
daemon token in memory; never print or log it. Registry additions require
user approval. Do not clear, reset, archive or send messages through the
guard.

Each bot saves its own checkpoint and local seal inside its own workspace.
The simple seal proves only that the save step ran: it does not prove the
last action or prevent a bot changing memory after sealing.

After any persistent bot model switch, each bot must quote a requested line
of a known file before performing review work. Report probe failures; do not
work around them. Persistent bots delegate substantive review, planning and
coding to task helpers.
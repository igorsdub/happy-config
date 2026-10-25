# happy-config

Version control for the live Happy instruction files in `~/Happy`.
Edit these files in place; no synchronization with a separate folder is needed.

Tracked files:

- `Config/AGENTS.md`: global working preferences.
- `Bots/chief_of_staff/AGENTS.md`: Chief of Staff coordination policy.
- `.gitignore`: explicit allowlist of files approved for version control.
- `README.md`: repository layout and restoration notes.

All other files are ignored by default. Review each new allowlist entry and
the staged diff before committing. Ignoring a file does not remove it from
Git history if it was previously committed.

## Restore on another installation

Clone this repository into a separate temporary folder, then copy the two
instruction files to the corresponding paths in that installation's Happy
folder after reviewing any existing instructions. On macOS the usual folder
is `~/Happy`; on Linux it is `~/happy`. Preserve other configuration files.

This repository contains instructions only. Provider authentication, secrets,
model configuration, and Happy's internal state must be set up separately.
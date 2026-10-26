# happy-config

Version control for live Happy instructions, selected configuration, and local
coordination tools in `~/Happy`.
Edit these files in place; no synchronization with a separate folder is needed.

Tracked files:

- `Config/AGENTS.md`: global working preferences.
- `Bots/chief_of_staff/AGENTS.md`: Chief of Staff coordination policy.
- `Config/happy.toml`: selected machine configuration, including new-chat defaults.
- `Bots/chief_of_staff/SPECIALISTS.md`: specialist roster and dispatch contract.
- `Bots/chief_of_staff/DISPATCH.md`: local dispatch-core usage and limitations.
- `Bots/chief_of_staff/tools/`: explicitly allowlisted dispatch support scripts.
- `Bots/chief_of_staff/tests/`: dispatch regression tests.
- Six specialist bot folders: their `AGENTS.md` roles and `INTAKE.md` templates.
- `.gitignore`: explicit allowlist of files approved for version control.
- `README.md`: repository layout and restoration notes.

All other files are ignored by default. Review each new allowlist entry and
the staged diff before committing. Ignoring a file does not remove it from
Git history if it was previously committed.

## Restore on another installation

Clone this repository into a separate temporary folder, then copy the selected
files to the corresponding paths in that installation's Happy folder after
reviewing existing instructions and machine-specific configuration. On macOS
the usual folder is `~/Happy`; on Linux it is `~/happy`.

Git does not restore Happy's bot registrations, conversations, credentials, or
daemon state. Recreate the bots and update installation-specific agent IDs in
the roster, role files, and dispatch mappings before using them elsewhere.
Keep credentials out of `happy.toml`; it is tracked and published.

## Dispatch core

The dispatcher supports routing, compact handoffs, read-only preflight, and
atomic local two-slot reservations. Real sends and aborts are disabled; actual
worker launches remain manual. See `Bots/chief_of_staff/DISPATCH.md`.

The runtime uses the Python standard library. Run its tests with pytest in a
local environment, for example from `Bots/chief_of_staff`:

```sh
uv venv .venv
uv pip install --python .venv/bin/python pytest
.venv/bin/python -m pytest tests/test_dispatch.py -q
```

The Unix-socket fixture needs host socket-binding permission. Runtime ledgers,
`.context/`, virtual environments, caches, and credentials remain ignored.
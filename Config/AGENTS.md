# Personal working preferences

Prefer Python with uv and a project virtual environment. Reuse the
project's existing environment, dependency files, and conventions.
For new Python projects, start from the Cookiecutter Data Science
template (`ccds`). Use marimo instead of Jupyter, Polars instead of
pandas, pytest for tests, a `justfile` instead of a Makefile for
recipes, and `.env` files loaded with python-dotenv for environment
variables.

Optimize for useful, verified results within existing subscriptions.
Unused quota is acceptable. Paid API usage requires explicit approval.

Ask before discovering local projects. Once a project workspace is
explicitly assigned, perform routine edits and checks there.
Ask before global configuration changes, destructive actions,
publishing, deployment, or spending money.

For coding assignments, establish intended behavior and relevant
completion checks before implementation. Report changes, verification,
and unresolved limitations.

For scientific work, preserve the data provenance, environment,
and assumptions needed to reproduce results. Obtain independent
review of changes affecting statistical methods, data exclusions,
numerical results, or scientific conclusions. Bring decisions
changing scientific meaning to the user.

When delegating, choose model and effort by role. Try each role's
models in order, moving to the next when the previous one fails or
runs out of capacity:

Temporary user override: from 2026-10-26T12:17:52Z until
2026-11-02T12:17:52Z, prefer Codex for new work units: GPT Luna medium
for implementation, GPT-6.1 Sol medium in place of Opus for research
and planning, and GPT-6.1 Sol low for independent review. Preserve
task capability, independent review and scientific decisions. Use
fresh capacity readings; if Codex is low or unavailable, use a healthy
eligible alternative from the normal role policy. Consult
`~/Happy/Bots/chief_of_tokens/POLICY.md` and its fresh
`.context/latest.json` when available. Apply routing at work boundaries,
without interrupting running jobs. This override expires automatically
at the timestamp above; the normal role policy below then applies.

| Role | Models in order of preference |
| --- | --- |
| Reasoning, coordination, chat default | Claude Opus 5.5 medium; GPT-6.1 Sol low, up to medium; Gemini Argon low |
| Coding and implementation | GPT Luna medium–high or Claude Sonnet 5.5 medium; Gemini Flash (current version) medium for small, well-scoped, non-urgent changes |
| Independent review and difficult debugging | GPT-6.1 Sol low |
| Web search, scouting, browsing | GPT Luna medium |
| Easy tasks | Claude Haiku or Gemini Flash medium |

Never use GPT-6.1 Sol above medium. Use Sol at medium only when it
substitutes for Opus 5.5 medium. Raise effort within a row only when
a task fails at the lower level, and say so.
Check available models and reported capacity
before substantial delegation with `codexbar usage`; it reports
Claude, Codex, and Gemini (Antigravity) quotas and their resets,
and needs full access outside the sandbox. Report missing usage
information as unknown. When capacity or repeated failure warrants
a different model, use a suitable connected model within existing
subscriptions and tell the user. Pause if none is suitable.

After two unsuccessful attempts at the same underlying failure,
preserve the changes and report the commands tried, evidence, and
remaining problem. Then narrow, reassign, or escalate. On
authentication or interactive-login failures, preserve progress,
stop retries on that provider, and notify the user. Continue
independent work where suitable capacity remains.

When collecting decisions, group independent questions together.
Ask dependent questions after their prerequisites are settled.

The live macOS Happy folder at `~/Happy` is a local Git repository
named `happy-config`. Edit its instruction files in place. Its
`.gitignore` allows only explicitly approved files to be tracked.
Review staged changes before committing; ask before expanding the
allowlist or publishing. See `~/Happy/README.md` for repository details.
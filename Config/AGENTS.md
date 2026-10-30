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

When delegating, choose model and effort by role. Persistent bot chats,
including every lead, run on Claude Sonnet 5.5 medium. The new-session
default is `anthropic/sonnet-5-5` at medium on provider `claude`. Opus
is used only as a short planner worker that writes its plan to a file
and stops. Literature Scout and Chief of Tokens are the session
exceptions: Claude Haiku 5.5 medium, with Sonnet 5.5 medium as fallback.
Try each role's models in order, moving to the next when the previous
one fails or runs out of capacity:

Temporary capacity window, recorded 2026-10-30T02:15:00Z. Claude's
five-hour session is exhausted until 2026-10-30T03:09:00Z (12:09 JST);
the Claude week is not exhausted. Codex's five-hour session is
exhausted until 2026-10-30T04:56:00Z (13:56 JST). Until the Claude
session resets, do not start Claude sessions or workers, and do not
use Grok 4.7 or Grok 4.6: they are heavier than this gap needs.
Sessions continue on Grok 4.5 medium (provider `grok`, model
`xai/grok-4.5`). Implementation and verification use Grok Build
medium (`xai/grok-build`). Composer 2.5 stays for easy tasks only
(effort off). Grok weekly was about 97% at this reading, so keep
those turns short. After 03:09Z, sessions return to Sonnet 5.5
medium (Haiku for Literature Scout and Chief of Tokens). Until
04:56Z, implementation and verification still skip Codex and use
Grok Build medium. This paragraph expires at 04:56Z. Grok stays
never above medium.

| Role | Models in order of preference |
| --- | --- |
| Session, coordination, chat default | Claude Sonnet 5.5 medium (Literature Scout and Chief of Tokens: Claude Haiku 5.5 medium); Grok 4.6 medium; Antigravity Claude Sonnet 5.5 medium; GPT-6.1 Terra medium |
| Research and planning (short planner worker) | Claude Opus 5.5 medium; GPT-6.1 Sol medium; Grok 4.7 medium; Antigravity Claude Opus 5.5 medium |
| Coding and implementation | GPT-6.1 Terra medium; Grok 4.6 medium; Claude Sonnet 5.5 medium; Antigravity Claude Sonnet 5.5 medium |
| Independent review and difficult debugging | GPT-6.1 Sol low; Grok 4.7 medium |
| Verification | GPT-6.1 Terra medium; Grok 4.6 medium; Claude Sonnet 5.5 medium. Different agent from the implementer. |
| Web search, scouting, browsing | Claude Haiku 5.5 medium; Claude Sonnet 5.5 medium; GPT Luna medium |
| Easy tasks | Claude Haiku 5.5 medium; Gemini Flash (current version) medium; Grok Composer 2.5; Antigravity Gemini Flash medium |

Never use GPT-6.1 Sol above medium. Use Sol at medium only when it
substitutes for Opus 5.5 medium. Never use Grok above medium. Prefer
ChatGPT models for implementation and review when they have capacity.
Raise effort within a row only when a task fails at the lower level,
and say so. Gemini Flash is for easy tasks only. Gemini and
Antigravity stay off reviews until file reads on those routes are
proven to return content (Antigravity reads have previously returned
only paths). Antigravity's Claude/GPT quota group is the preferred
Antigravity fallback; do not use its Gemini models for review,
planning, or implementation. Scientific and statistical changes get
an independent review by a different agent, from a different model
family where possible. Scientific decisions stay with the user.
Heavier use of the Grok subscription is allowed until 2026-11-30; it
will then be downgraded. Grok stays never above medium.

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
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
including every lead, Literature Scout, and Chief of Tokens, run on
Claude Sonnet 5.5 **low**. The new-session default is
`anthropic/sonnet-5-5` at **low** on provider `claude`. Opus is used
only as a short planner worker that writes its plan to a file and
stops. Default effort is **low** wherever a dial exists; raise one
step only after that stage fails. Try each role's models in order,
moving to the next when the previous one fails or runs out of capacity:

Temporary capacity note, updated 2026-10-30T03:40:00Z. Bot sessions are
back on Claude Sonnet 5.5 low (user). Codex's five-hour session may
still be exhausted until 2026-10-30T04:56:00Z (13:56 JST): until then,
implementation may use Grok Build medium (`xai/grok-build`) and
independent review may use Grok 4.7 **low** marked provisional. After
04:56Z prefer Codex Terra/Sol again when capacity allows. Composer 2.5
stays for easy orchestration only (effort off). Grok stays never above
medium. This Codex-gap sentence expires at 04:56Z.

Work pattern (user-adopted 2026-10-30): a cheap task dispatcher holds a
short checkpoint; reuse planner/implementer only inside one hot ticket;
start a new reviewer and check runner every pass; do not keep standing
four-role chats. Prompt caching does not justify durable role
transcripts across tickets.

| Role | Models in order of preference |
| --- | --- |
| Session, coordination, chat default | Claude Sonnet 5.5 low; Grok 4.5 low; Antigravity Claude Sonnet 5.5 low; GPT-6.1 Terra low |
| Research and planning (short planner worker) | Claude Opus 5.5 low; GPT-6.1 Sol low; Grok 4.7 low; Antigravity Claude Opus 5.5 low |
| Coding and implementation | GPT-6.1 Terra low; Grok Build medium (medium-only overflow); Claude Sonnet 5.5 low; Antigravity Claude Sonnet 5.5 low |
| Independent review and difficult debugging | GPT-6.1 Sol low; Grok 4.7 low (provisional if same family as implementer) |
| Verification | GPT-6.1 Terra low; Grok Build medium; Claude Sonnet 5.5 low. Different agent from the implementer. |
| Web search, scouting, browsing | Claude Sonnet 5.5 low; Claude Haiku 5.5 low; GPT Luna low |
| Easy tasks / orchestration | Claude Haiku 5.5 low; Grok Composer 2.5 (off); Gemini Flash (current version) low; Antigravity Gemini Flash low |

Never use GPT-6.1 Sol above medium. Use Sol at medium only when it
substitutes for Opus 5.5 and low has already failed. Never use Grok
above medium. Prefer ChatGPT models for implementation and review when
they have capacity. Raise effort within a row only when a task fails at
the lower level, and say so. Gemini Flash is for easy tasks only. Gemini and
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

Question budget (user-adopted 2026-11-01): approving a plan authorizes
everything it lists: edits, workers, reviews, messages and checks, with no
per-step approval. Ask the user only for commit, push, publish, deploy,
spending money, scope change, or scientific decisions, plus local-project
discovery, destructive actions and allowlist expansion unless the approved
plan lists them. Ask in at most two rounds per task: round one is a single
consolidated set of questions plus the plan approval, with documented
assumptions in the plan; round two, at the end, covers commit and push. The
plan gate is a single approval covering the whole plan. Decisions needed
before affected work (spending, scope, scientific) belong in round one; if an
unforeseen one arises, pause and ask. Never re-ask a decision the user has
explicitly approved; an assumption or worker-written note is not approval.
Auto-mode reviews and staged edits inside the approved scope are not asked
about. A plan lists the global-configuration edits it makes, so the "ask
before global configuration changes" rule is met by plan approval.

The live macOS Happy folder at `~/Happy` is a local Git repository
named `happy-config`. Edit its instruction files in place. Its
`.gitignore` allows only explicitly approved files to be tracked.
Review staged changes before committing; ask before expanding the
allowlist or publishing. See `~/Happy/README.md` for repository details.
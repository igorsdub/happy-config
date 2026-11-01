# Quota and routing policy

## Reading discipline

Use `codexbar usage --provider codex --format json --status`, then the equivalent for `claude` and `antigravity` when configured and healthy. For Antigravity only, if CodexBar yields unavailable, stale, partial, or unknown quota data, use the supported local CLI command `agy -p /usage --output-format json --print-timeout 30s` as a fallback. Do not use the fallback after an authentication failure or provider outage; auth failures stop collection until the user confirms recovery/settings changed. Do not retry interactive login or query unrelated providers. CodexBar account usage remains authoritative when valid; successful `agy /usage` output is a direct Antigravity account reading. `agent_options` percentages are model-group estimates, not account quota, unless a separate source explicitly verifies their semantics.

For `agy` output, preserve each named quota group and its own windows/reset timestamps. Do not combine or sum shared pools. The `Gemini Models` group explicitly shares its reported limits across Gemini Flash and Gemini Pro; `Claude and GPT models` is a separate shared group. `Gemini 4 Argon` is a distinct group: record only windows actually reported there and do not infer a 5-hour limit from another group. Direct Claude subscription data remains separate from Antigravity-hosted Claude/GPT group limits. The CLI response does not provide a provider sample timestamp, so record the monitor observation time as the sample time and label its basis; do not retain raw payloads or credentials.

Record sample time and age. Consider a reading fresh for up to two hours; stale, materially future-dated, or malformed data is unknown, never zero. Preserve known independent windows if another window is absent, but mark the provider partial and do not claim the tightest quota is known. A reset window must have a valid future reset timestamp. Calculate remaining capacity as `100 - usedPercent`; the smallest remaining percentage among windows caps availability. Never compare usage deltas across a reset boundary; compare only samples with matching window duration and reset timestamp. Repeated input tokens are agent-reported throughput, not subscription burn. Account quota-use rate is reported only when two fresh observations share the same window and reset identity.

Keep normalized state only: provider and source, sample timestamp/basis, windows (duration, reset timestamp, remaining percent), named quota groups, health, exact credit expiry timestamps, last alert keys/severities, and next scheduled check. Exclude raw payloads, credentials, account emails, and credit IDs.

## Eligible routes

Established routing outside a valid priority window. Persistent bot
chats, including every lead, Literature Scout, and Chief of Tokens,
use the bot-model line in `Config/AGENTS.md`. Opus is a short planner
worker only. Grok is never above medium. Sol is never above medium.
Prefer ChatGPT models for implementation and review when they have
capacity.

| Work | Route |
| --- | --- |
| Session / coordination (task workers; bot chats use the bot-model line in `Config/AGENTS.md`) | Claude Sonnet 5.5, low; if unavailable, Grok 4.5 low; then Antigravity Claude Sonnet 5.5 low; then GPT-6.1 Terra low |
| Critical implementation | GPT-6.1 Terra, low; if unavailable, Grok Build medium; then Claude Sonnet 5.5 low; then Antigravity Claude Sonnet 5.5 low |
| Routine implementation | GPT-6.1 Terra, low; if unavailable, Grok Build medium; then Claude Sonnet 5.5 low; then Antigravity Claude Sonnet 5.5 low |
| Research/planning | Claude Opus 5.5, low (short worker); if unavailable, GPT-6.1 Sol low; then Grok 4.7 low; then Antigravity Claude Opus 5.5 low |
| Independent review | GPT-6.1 Sol, low; if unavailable, Grok 4.7 low (provisional if same family). Not Gemini or Antigravity until file reads return content. |
| Verification | GPT-6.1 Terra, low; if unavailable, Grok Build medium; then Claude Sonnet 5.5 low. Different agent from the implementer. |

For coding, Gemini Flash (current catalog version) low is a final fallback only for small, well-scoped, non-urgent work. The collector includes it only when `check --small-scoped-non-urgent` explicitly supplies that work context; generic monitoring leaves it out. Flash is never a critical-work fallback and is not a review, planning, or implementation route. Coding starts with `openai/gpt-6.1-terra` at low, then Grok Build medium (medium-only overflow), then Claude Sonnet 5.5 low. Every bot session, including Literature Scout and Chief of Tokens, uses the single bot-model line in `Config/AGENTS.md`. Easy orchestration may use Claude Haiku low or Composer 2.5 (off); this collector does not select an easy-task route. Antigravity's Claude/GPT quota group is the preferred Antigravity fallback; its Gemini models stay off reviews, planning, and implementation. Default effort is low; raise one step only after a stage fails.

Choose in the listed preference order, not by maximum percentage: the established route is first. Select a route only when its provider has a fresh, healthy, complete reading and at least 20% remaining in every relevant window. If the preferred provider is unavailable or below 20%, use only a listed, quality-capable fallback that independently meets those checks. Otherwise emit `NEEDS_CAPACITY_CHECK` with no selected model. Model IDs remain advisory and must be validated against the current catalog before launch. At or below 10%, mark the provider urgent and notify the Chief. Never downgrade critical work to Flash or lower effort to consume quota. Unknown/stale values never establish availability.

User update, 2026-10-30: heavier use of the Grok subscription is allowed until 2026-11-30; it will then be downgraded. Grok stays never above medium.

Temporary capacity note, updated 2026-10-30T03:40:00Z. Until 2026-10-30T04:56:00Z do not select Codex for implementation/review if its five-hour window is still exhausted; use Grok Build medium for implementation and Grok 4.7 low (provisional) for review. After 04:56Z prefer Codex Terra/Sol when capacity allows. Composer 2.5 is easy orchestration only. Default effort is low; raise one step only after a stage fails. This Codex-gap sentence expires at 04:56Z.

## Alerts and credits

When a fresh reading confirms a five-hour quota reset, send the user a short nudge in this bot's chat: name the provider or quota group, the remaining five-hour percentage, and any weekly quota that still limits use. For example: "Codex's five-hour quota has reset — 100% available; weekly quota is 66%. Fresh capacity is ready for your next work." Confirm a reset from an elapsed previous reset boundary, a later reset timestamp, and increased remaining capacity in comparable healthy readings; a moving timestamp alone is routine jitter. Use only reported five-hour windows. Send once per confirmed reset, even if routing stays the same; combine simultaneous resets into one message. Record successful delivery under a distinct `reset-nudge` alert key containing provider, group/window identity, and the new reset timestamp, and suppress that key permanently for that reset. Keep an undelivered nudge in normalized local state for retry on the next cycle. This user-requested nudge is an exception to reporting only material route changes to the Chief. Detection happens on the existing monitoring wakes; retain the documented cadence and single wake chain.

Suppress the same alert key and severity for six hours. Immediately report a new severity, provider authentication failure/hard outage, reset-credit availability/expiry threshold crossing, or a material reset change. Alert at 72 hours and again at 24 hours before an exact reported credit expiry. No redemption, purchase, paid API use, or credit-consuming experiment is authorized.

## Cadence and messaging

User preference, 2026-10-29: show every time in user-facing messages in Japan time (JST, UTC+9), labelled "JST". Keep stored state, schedules, and logs in UTC.

Bot context maintenance (user decision 2026-11-01; supersedes the Chief-only periodic run): every 30 minutes, run `python3 tools/context_maintenance.py --bot chief_of_staff --bot literature_scout maintain` in `/Users/igorsdubanevics/Happy/Bots/chief_of_staff` exactly once with reviewed full access while `.context/context-maintenance-pilot.json` has status `pilot`; after 24 hours and one compaction observed as `completed`, set status `all` and run `--all maintain` instead. Read its `CONTEXT_MAINTENANCE.md` first. Persist the JSON locally. Routine `skip` and `completed` outcomes need no message. Forward any `report` field (a bot skipped three cycles in a row) to the Chief once. Stop maintenance (set status `stopped`) and alert the Chief with the JSON on `pending_unknown`, `rejected`, `error_fail_closed`, a nonzero exit, a failed compaction, or a review denial. Never loop, retry, clear, or use `clear-pending`. Credit redemption remains unauthorized.

Check every two hours. Use a one-hour interval for an exact credit expiry within 24 hours or meaningful low-capacity risk; a reset within one hour warrants an hourly check only when low-capacity recovery depends on it. Reset imminence with high remaining quota alone does not shorten cadence. Never check faster than 15 minutes. Schedule one durable wake to self and retain its ID/due time in state; replace rather than stack a wake. On each wake, clear the consumed schedule reference, collect once, update state atomically, report only material alerts to the Chief, and schedule the next wake. Do not broadcast or interrupt active work. Messages advise next-work-unit selection only; they do not force-switch models, edit drafts, launch/abort workers, or change dispatch configuration. Scheduling and notification delivery depend on Happy daemon/host availability; catch up on resume.
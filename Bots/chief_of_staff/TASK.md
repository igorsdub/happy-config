# Task

## When to use a task

Create a task (`create_task`) for every code, script or policy-file change. For a single-file change with an obvious test, use the short task: skip research and planning, but use an implementer and a fresh reviewer. Other research, answers and read-only work go to a single worker or subtask. Repository work inside a task runs in subtasks, at most two levels deep.

## Roles and models

All roles use low effort except Grok Build, which uses medium. Before starting each role, check capacity with `codexbar usage` and record the model and any fallback reason in the checkpoint. Report unavailable capacity information as unknown.

| Role | Models in order | Responsibility |
| --- | --- | --- |
| Orchestrator | Sonnet 5.5, Grok 4.5 | Task chat; maintain `.context/checkpoint.md`, about 40 lines at most. |
| Researcher | Sonnet 5.5, Haiku 5.5 | Only when facts are missing; write `.context/research.md`. |
| Planner | GPT-6.1 Sol low, Grok 4.7 low, Claude Opus 5.5 low (only if Grok is unavailable) | Group independent questions; ask dependent questions after prerequisites. Write `.context/plan.md`, then stop. |
| Implementer | Terra, Grok Build medium, Gemini Flash | Own workspace or subtask. Flash is low effort and only for easy, low-risk tickets; otherwise pause and ask. |
| Reviewer | Sol, Grok 4.7 | Fresh agent each pass; a different agent and, where possible, model family. Grok review is provisional if the implementer is also Grok. Give only the plan, diff and checks, never the implementer's transcript. |
| Check runner | Terra, Grok Build medium | Fresh agent each pass, never the implementer. |

## Handoff template

Send one message containing:

```text
Goal:
Scope (allowed paths; forbidden paths):
What the task may decide alone:
Decisions already made:
Acceptance checks:
Deliverable:
Approval needs (touches ~/Happy, public release, or new repo?):
Requester's agent ID:
ETA (JST):
```

## Orchestrator checkpoint template

Keep `.context/checkpoint.md` to about 40 lines or fewer:

```text
Goal and scope:
Status and next action:
Decisions and approval needs:
Plan, diff and check locations:
Review verdicts and open findings:
Role models, capacity and fallback reasons:
Worker tokens and context windows:
Blockers and requester ID:
```

## Ticket boundaries

A ticket has one goal and one acceptance set; a new ticket means a new task. Reuse the planner and implementer only inside one hot ticket, compacting before reuse. Archive them when the ticket finishes or pauses, the next ticket is unrelated, they are idle past the provider cache lifetime (Claude 5 minutes; Codex about 30 minutes; Grok and Gemini are cold), or they reach about 120k tokens. 200k is a hard limit. Every worker ends its completion message with tokens used and context window.

## Review rounds

Every pass uses a fresh reviewer and a fresh check runner. The reviewer returns:

```text
Verdict: PASS | PASS-WITH-NITS | FAIL
Findings:
- P1 | P2 | P3 — file:line — finding — fix
```

P1 blocks acceptance: wrong, unsafe, or violates the spec or policy. P2 should be fixed in this ticket; the orchestrator may waive it and must list it in the final report. P3 is an optional note. Send the implementer only the findings text for fixes. A P1 or unwaived P2 starts a fix round. Allow at most two fix rounds; if P1 remains open, the planner narrows the scope once, then one more implementation and review round follows. If the narrowed version fails review, ask the user. After the cap, if only unwaived P2 findings remain, the orchestrator must waive them with reasons in the final report, narrow the scope, or escalate to the user.

## Authorization

The user's OK is required for commits, pushes and publishing in `~/Happy`, public releases and new repos. Project repositories retain the lead's existing Git autonomy, including inside a task. Leave `~/Happy` edits staged for review; the orchestrator asks using `request_user_input`, shows the exact `git diff --cached`, and relays the user's answer verbatim to the worker. If review still blocks the action, point the user to that worker's chat.

Do not install or write outside the workspace. Use a project venv and local cache (`uv`, `npm --prefix`). Report sandbox denials and never work around them. Make no global configuration or model changes.

## Reporting

Message the requester only on completion, an unremovable blocker, a user decision, or a critical misunderstanding. The final report contains outcome, changed files and diff link, checks with output, review verdict history, open P2 and P3 findings, models and fallback reasons, and each worker's tokens.

## Requesting bot

1. Delegate all code and policy file reading, editing and writing through a task (`create_task` or `send_task_message`); receive only the final result. Create the task and send the handoff once.
2. Do not poll; wait for the reply.
3. Pass to the user only what needs the user.
4. Archive the task after accepting the result.

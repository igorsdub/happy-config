# Scientific specialist bots

This is the Chief of Staff's dispatch directory. These persistent bots provide
role instructions and task handoffs using the installed Happy tools and skills.
The example products in the earlier research are references, not installed services.

| Assignment | Agent ID | Job model policy |
| --- | --- | --- |
| Literature discovery and evidence synthesis | l2v0wqznxkuxio59kgbrgss7 | Opus 5.5 medium → Sol 6.1 medium → Argon low |
| Scientific software and pipeline implementation | c7jcjdr4spvqm1hmd004qeus | Sonnet 5.5 medium for critical work; Flash medium only for easy routine code |
| Computational reproduction and provenance | ji7nybv1q0zpnd1umw2cehi5 | Research/planning route; implementation classified by risk |
| Independent statistical and methods review | yhx0xo1ar5pmj010k3cjm7ew | GPT-6.1 Sol low |
| Dataset schemas, quality and transformation lineage | lchx1u0x2tmj50aolsxt7q52 | Gemini 3.8 Flash medium |
| Manuscript drafting, captions and editorial critique | s71nrbudmd61u5vw0fvge0z2 | Research/planning route for evidence synthesis and planning |

## Dispatch

Read DISPATCH.md before preparing a job. The reviewed local core provides
routing, preflight, compact previews and atomic two-slot reservations via
tools/dispatch.py. Real sends/aborts are disabled; actual launches remain manual.

1. Reuse an existing suitable task or workstream. Send the relevant bot a scoped
   assignment through `send_agent_message`; include the owning task Agent ID.
2. Include objective or scientific claim, explicitly assigned project/workspace,
   inputs and provenance, requested output, completion checks, dependencies,
   scientific decisions reserved for the user, independent reviewer, and ETA.
   Classify implementation risk: critical work uses Claude Sonnet 5.5 medium
   first, then a capable ChatGPT model if needed; Flash is limited to easy,
   low-risk routine code. Unknown risk is not permission to select Flash.
   Pin the selected model per job attempt and record fallback reasons.
   Research/planning uses Opus 5.5 medium first, then GPT-6.1 Sol medium
   if unavailable, then Argon low if both are unavailable. Record the
   unavailable-model reasons; review continues to use Sol low.
3. Schedule at most two active workers under this coordinator, including bot-led
   delegates. Record the assignments before dispatch; a bot requests a slot before
   creating another worker. This is a coordination rule, not a software lock.
4. A bot performs repository work through project-bound subtasks and returns file
   references, verification, findings and open decisions. Keep scientific review
   independent from the implementation author. Assign a different reviewer if
   the Statistical Reviewer authored the analysis in question.
5. Rely on completion/blocker messages; follow the ETA and usage policy in AGENTS.md.
   Route results to the owning task as well as the coordinator. Keep bots idle
   between authorized assignments; creation is not permission for background work.

## Completion checks

Role setup is complete when each bot has saved and read back its own AGENTS.md
and INTAKE.md, demonstrated Happy tool access, and sent a readiness report.
These checks verify configuration and messaging. Dataset access, scientific
packages, external integrations, and analysis pipelines require assignment-specific
verification. A model selection is a starting session mode and role preference;
it is not automatic cross-model fallback or quota enforcement.

## Setup readiness

- Literature Scout: ready; saved/read AGENTS.md and INTAKE.md and called
  Happy agent_options successfully on Gemini 4 Argon low.
- Research Software Engineer: ready; the same file and Happy tool checks
  passed on Gemini 3.8 Flash medium.
- Reproducibility Engineer: ready; file readbacks and Happy tool check
  passed on Gemini 4 Argon low.
- Statistical Reviewer: ready; protected AGENTS.md write passed review,
  both file readbacks and Happy tool check passed on GPT-6.1 Sol low.
- Data Steward: ready; both file readbacks and Happy tool check passed
  on Gemini 3.8 Flash medium.
- Scientific Writer: ready; both file readbacks and Happy tool check
  passed on Gemini 4 Argon low.

All six initial provider/model/effort selections were verified through the
Happy API after readiness reports on 2026-10-25. Job-specific risk routing now
overrides those initial modes, including Research Software Engineer's original
Flash selection. Current runtime selection must be checked for each assignment.

Antigravity bots route independent Sol review through Chief of Staff to the
existing Statistical Reviewer; they need not start Sol on their own harness.
# Chief of Staff Dispatch Layer (`tools/dispatch.py`)

A narrow, durable dispatch and coordination layer for Chief of Staff managing six persistent scientific specialist bots in Happy Agent.

Designed according to deep module principles: a compact, auditable interface backed by a durable SQLite ledger, atomic process admission, capability preflight, and transport isolation.

---

## 1. Architecture & Core Seams

```
┌────────────────────────────────────────────────────────────────────────┐
│                          CLI / Coordinator                             │
│  submit · preview · preflight · dispatch · complete · cancel · rec     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
       ┌────────────────────────────┴────────────────────────────┐
       ▼                                                         ▼
┌───────────────────────────────┐       ┌───────────────────────────────┐
│           JobLedger           │       │         HappyAdapter          │
│   Atomic 2-worker limits      │       │     Stdlib HTTP Connection    │
│   Per-agent exclusivity       │       │     Fail-closed preflight     │
│   Provider health table       │       │     Stable send ID post       │
│   Compare-and-swap claim      │       │     Abort acknowledgement     │
└───────────────┬───────────────┘       └───────────────┬───────────────┘
                │                                       │
                ▼                                       ▼
        SQLite WAL DB                           Transport Seam
     (.context/dispatch.db)                 (UnixSocket / FakeTransport)
```

### Deep Module Seams:
1. **`JobLedger`**: SQLite durable store with WAL mode and `BEGIN IMMEDIATE` transaction isolation. Governs atomic admission, attempt counters, failure categorization, provider auth health, and state transitions without holding database transactions across network calls.
2. **`HappyAdapter`**: Client for the Happy Agent Base API (`/v0/agents/:id`, `/mode`, `/send`, `/abort`). Uses Python's standard-library `http.client.HTTPConnection` over Unix sockets with compliant framing (CRLF CRLF, chunked decoding) and fail-closed metadata validation.
3. **`HandoffRenderer`**: Generates compact, token-efficient assignment handoffs with scientific provenance, reproducibility assumptions, and explicit completion instructions instead of unbounded conversation transcripts.
4. **`DispatchCoordinator`**: High-level orchestration facade tying admission, preflight, non-mutating preview envelope generation, compare-and-swap send claims, and terminal evidence collection together.

---

## 2. Core Guarantees & Regression Coverage

All core guarantees and review edge cases are verified by the automated test suite in `tests/test_dispatch.py`:

| Guarantee | Enforcement Mechanism | Verified Failure / Edge Case Behavior |
| :--- | :--- | :--- |
| **1. No phantom sends on cancel** | Compare-and-swap `claim_for_send()` transitions `reserved` -> `sending` immediately before socket write. | If job is cancelled during preflight, `claim_for_send()` fails. **Zero network messages sent**. No rogue worker or freed slot. |
| **2. Terminal stopped proof required** | `complete` requires result evidence AND an explicit `--stopped-attestation`. An idle observation alone is not proof that this message finished. | `complete` without attestation is rejected (`InvalidStateError`), even if the agent reports idle. Slot retained. |
| **3. Abort acknowledgement is not stop** | HTTP 202 abort places job in `cancel_pending`; slot stays occupied. | Slot is released only by an explicit `--stopped-attestation`. |
| **4. Mode preflight fails closed** | `GET /mode` is the last submitted mode (`null` before the first message), not a lock. Missing `mode` key, malformed fields, auth/HTTP errors, or a model outside the catalog reject launch. A different current mode on an idle agent is allowed: the send carries the new mode. | Busy agents are never messaged or steered (not counted as a failure). |
| **5. Non-mutating preview** | `preview` (and dry-run `dispatch`) evaluates admission feasibility and preflight without mutating DB. | Leaves the job `queued` with no reservation. (`dispatch --live` is currently disabled; see the final section.) |
| **6. Provider-scoped auth blocking** | 401/403 errors persist provider health as `blocked`. Blocks all subsequent jobs for that provider. | Prevents repeated auth hammering across independent jobs until `unblock-provider` is called. |
| **7. Centralized credential redaction** | `sanitize_error_message()` scrubs tokens, keys, passwords, and `Bearer <token>` across all paths. | Exceptions, error outputs, CLI errors, and ledger audit events never leak credentials. |
| **8. Unblock fresh attempt budget** | `reconcile --action unblock` resets `attempt_count = 0` and failure counters. | Prevents immediate re-blocking of previously exhausted jobs after bug fixes. |
| **9. Multi-process concurrency** | Tested via independent subprocesses racing for SQLite locks. | At most two reservations succeed globally; target agent exclusivity is preserved. |

---

## 3. Specialist Bot Directory

The dispatch layer maintains built-in mappings to the six authorized specialist bots from `SPECIALISTS.md`:

| Assignment Alias | Target Agent ID | Pinned Provider | Pinned Model | Pinned Effort | Role Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `literature` | `l2v0wqznxkuxio59kgbrgss7` | routed | by risk | by risk | Literature discovery and evidence synthesis |
| `software` | `c7jcjdr4spvqm1hmd004qeus` | routed | by risk | by risk | Scientific software and pipeline implementation |
| `reproducibility`| `ji7nybv1q0zpnd1umw2cehi5` | routed | by risk | by risk | Computational reproduction and provenance |
| `review` | `yhx0xo1ar5pmj010k3cjm7ew` | routed | by risk | by risk | Independent statistical and methods review |
| `data` | `lchx1u0x2tmj50aolsxt7q52` | routed | by risk | by risk | Dataset schemas, quality and lineage |
| `manuscript` | `s71nrbudmd61u5vw0fvge0z2` | routed | by risk | by risk | Manuscript drafting, captions and critique |

---

## 4. CLI Usage & Commands

```bash
# 1. Submit a job (idempotent for identical payload; rejects conflicts)
python3 tools/dispatch.py submit \
  --id job_seq_001 \
  --owner fhti51x1qapqy7grqm3xoref \
  --target software \
  --objective "Implement sequence fitness pipeline validation" \
  --inputs "data/fitness.parquet, src/pipeline.py" \
  --provenance "Replicate 1-3 fitness assay; seed 42" \
  --acceptance "Run pytest and verify R2 > 0.90" \
  --eta 15

# 2. Run readiness and capability preflight (fails closed)
python3 tools/dispatch.py preflight --id job_seq_001

# 3. Preview dispatch envelope (strictly non-mutating; holds 0 slots)
python3 tools/dispatch.py preview --id job_seq_001

# 4. Live dispatch: DISABLED in this release; fails closed with no ledger change (see final section)
python3 tools/dispatch.py dispatch --id job_seq_001 --live

# 5. List jobs by status (queued, reserved, sending, running, completed, blocked, cancelled, cancel_pending)
python3 tools/dispatch.py list --status running

# 6. View job details, audit events, and rendered handoff
python3 tools/dispatch.py show --id job_seq_001

# 7. Complete job (requires result evidence AND stopped proof)
python3 tools/dispatch.py complete \
  --id job_seq_001 \
  --evidence "Pytest passed: 14 tests, R2 = 0.942 on validation split." \
  --stopped-attestation "Verified worker process exited and agent is idle"

# 8. Cancel job (holds slot in cancel_pending until stopped proof)
python3 tools/dispatch.py cancel \
  --id job_seq_001 \
  --stopped-attestation "Operator verified agent idle via UI"

# 9. Reconcile an ambiguous, blocked, or pending job
python3 tools/dispatch.py reconcile \
  --id job_seq_001 \
  --action unblock \
  --evidence "Authorizing fresh attempt budget after fixing inputs"

# 10. Restore health for a blocked provider
python3 tools/dispatch.py unblock-provider --provider antigravity
```

---

## 5. Scope & Platform Boundaries

1. **Wrapper-Only Enforcement**: The dispatch layer governs jobs submitted and admitted through it. Raw sends via the Happy UI, external tools, or direct API calls bypass this ledger.
2. **Unix Domain Socket Transport**: Connections to the Happy daemon (`~/.happy/agent/server.sock`) require host filesystem and socket access. Inside macOS sandbox environments that restrict arbitrary Unix domain socket connections, use `preview` for envelope verification. Read-only preflight works with host access; live dispatch is disabled on every host (see the final section).
3. **No Automatic Lease Expiry**: An ETA is an operational guideline and a prompt for operator review, **never** an automatic timeout that releases a running slot.
4. **Explicit Fallback Only**: Pins are immutable per job. Critical implementation routes to Claude Sonnet 5.5; ChatGPT Luna is selected only when `--claude-unavailable REASON` is given or `claude` provider health is blocked, and the reason is stored in `route_reason`. No automatic quota detection or failover exists; no paid API is used.
5. **No Network Inside SQLite Transactions**: Network I/O is strictly isolated outside database transactions, preventing database locks during transport lag.

## Routing policy and criticality

`submit` takes `--risk critical|routine` (omitted = fail safe to `critical`; invalid values rejected) and `--kind implementation|research|review` (default from the roster). `select_route` is a pure function; the job stores `kind`, `risk`, provider/model/effort, and `route_reason`, and each `admit` event records the pins used for that attempt.

| Kind / risk | Route (provider, model, effort) |
| --- | --- |
| implementation, critical or unspecified | `claude`, `anthropic/sonnet-5-5`, medium |
| implementation, critical, Claude declared unavailable | `codex`, `openai/gpt-6-luna`, medium (explicit reason recorded) |
| implementation, routine | `antigravity`, `antigravity/gemini-3.8-flash`, medium |
| research / planning (`--kind planning` is an alias) | `claude`, `anthropic/opus-5-5`, medium |
| research / planning, Claude declared unavailable (`--claude-unavailable`) | `codex`, `openai/gpt-6.1-sol`, medium (user-authorized Opus substitute) |
| research / planning, Claude and Codex both declared unavailable (`--codex-unavailable`) | `antigravity`, `antigravity/gemini-4-argon`, low (never a silent default) |
| review | `codex`, `openai/gpt-6.1-sol`, low |

Guards: Flash is rejected for any non-routine job; Argon only for research/planning and only after both unavailability reasons are recorded (flags or persisted `claude`/`codex` provider health); overrides must match a catalog triple. The daemon revalidates mode against its live catalog at send (400 maps to a definite rejection, job returns to `queued` and counts a strike).

## Wire and lifecycle notes

- `POST /send` succeeds with `202`; the receipt must echo our message `id`. A receipt proves acceptance only, never completion.
- Unknown network outcome (timeout, bad receipt) keeps the slot reserved; resend with the same `id` is documented as idempotent but is not automated.
- Completion is by manual/pushed `complete` with attestation; there is no polling daemon. Message/run metadata (`GET /messages`, `runId`) is not yet consulted automatically: the attestation is the audit record.
- Not implemented: automatic quota or model failover, live message-state verification. Preflight is read-only; live send has not been exercised against a real daemon.
- Abort is always guarded: `POST /abort {"expectedRunId": ...}` using the `runId` from the send receipt (stored as `run_id`). A different active run returns 409. With no known run ID no abort is sent; the job stays `cancel_pending` until a manual stop and `--stopped-attestation`. An abort 202 is acknowledgement, not proof of stop. A pending message has `runId: null`, so a queued send to a busy agent has no abortable ID.
- HTTP framing is tested against a real Unix-socket server (test_22); the test needs socket binding, which the default sandbox blocks.

## Live dispatch is DISABLED (narrowed core)

Two independent reviews reproduced a send/cancel race (a cancel with a truthful "idle" attestation frees the slot while the original sender is mid-send, so another job is admitted to the same agent). Live integration is therefore deferred and **this release does not enforce actual worker launches**.

- `HappyAdapter.send_assignment` / `abort_agent` raise `LiveMutationDisabledError` for any transport that does not set `allows_live_mutation = True`. The real `UnixSocketTransport` never does; no flag bypasses it. Only the in-memory `FakeTransport` (test-only) opts in.
- `DispatchCoordinator.dispatch(live)` and CLI `dispatch --live` fail closed before any ledger change; nothing is reserved or sent. `cancel` never issues an abort on the real transport.
- Ledger transitions `cancel`, `complete`, and `reconcile confirm_stopped|confirm_running` are rejected while a job is `sending`.
- Usable now: `submit`, `list`, `show`, `preview`, read-only `preflight`, atomic admission ledger, routing policy, manual `complete`/`cancel` with attestation. The send/abort code is preserved for a later redesign.
- Routing overrides must equal the policy-selected route for the stated availability; they cannot skip rungs or relax effort.

### Local manual ledger use (no worker launch)

`python3 tools/dispatch.py admit --id JOB_ID` reserves a ledger slot using the existing atomic admission (max two active jobs, one per agent). It never contacts Happy and does **not** launch or message a worker; repeating it on a held job is a no-op. A reservation is released only by an explicit attestation:

```
python3 tools/dispatch.py cancel --id JOB_ID --stopped-attestation "operator: nothing was launched"
python3 tools/dispatch.py complete --id JOB_ID --evidence "..." --stopped-attestation "..."
```

#!/usr/bin/env python3
"""
Chief of Staff Dispatch Layer
------------------------------
Atomic admission, capability preflight, durable SQLite job ledger,
compact handoffs, and safe transport adapter for scientific specialist bots.

Designed according to codebase-design principles (deep module, small interface, clean seams).
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import http.client
import json
import os
import pathlib
import re
import secrets
import socket
import sqlite3
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

# ---------------------------------------------------------------------------
# Specialist Bot Registry (from SPECIALISTS.md)
# ---------------------------------------------------------------------------

# Installed model catalog (provider, model id, effort) as the Happy mode API names them.
MODEL_CATALOG: Dict[str, Tuple[str, str, str]] = {
    "opus": ("claude", "anthropic/opus-5-5", "medium"),
    "sonnet": ("claude", "anthropic/sonnet-5-5", "medium"),
    "sol_med": ("codex", "openai/gpt-6.1-sol", "medium"),
    "luna": ("codex", "openai/gpt-6-luna", "medium"),
    "sol": ("codex", "openai/gpt-6.1-sol", "low"),
    "flash": ("antigravity", "antigravity/gemini-3.8-flash", "medium"),
    "argon": ("antigravity", "antigravity/gemini-4-argon", "low"),
}

# Specialist roster. `kind` drives routing; provider/model/effort are the routine
# default for that role and are NOT used for critical implementation (see select_route).
SPECIALISTS: Dict[str, Dict[str, str]] = {
    "literature": {"agent_id": "l2v0wqznxkuxio59kgbrgss7", "role": "Literature discovery and evidence synthesis", "kind": "research"},
    "software": {"agent_id": "c7jcjdr4spvqm1hmd004qeus", "role": "Scientific software and pipeline implementation", "kind": "implementation"},
    "reproducibility": {"agent_id": "ji7nybv1q0zpnd1umw2cehi5", "role": "Computational reproduction and provenance", "kind": "research"},
    "review": {"agent_id": "yhx0xo1ar5pmj010k3cjm7ew", "role": "Independent statistical and methods review", "kind": "review"},
    "data": {"agent_id": "lchx1u0x2tmj50aolsxt7q52", "role": "Dataset schemas, quality and transformation lineage", "kind": "implementation"},
    "manuscript": {"agent_id": "s71nrbudmd61u5vw0fvge0z2", "role": "Manuscript drafting, captions and editorial critique", "kind": "research"},
}
_DEFAULT_MODEL_KEY = {"research": "opus", "review": "sol", "implementation": "flash"}
for _spec in SPECIALISTS.values():
    _spec["provider"], _spec["model"], _spec["effort"] = MODEL_CATALOG[_DEFAULT_MODEL_KEY[_spec["kind"]]]

KINDS = ("implementation", "research", "planning", "review")  # planning is an alias of research
RISKS = ("critical", "routine")


class RoutingError(Exception):
    """Raised when a job's model route violates the routing policy."""


def select_route(
    kind: str,
    risk: Optional[str] = None,
    override: Optional[Tuple[Optional[str], Optional[str], Optional[str]]] = None,
    claude_unavailable: Optional[str] = None,
    codex_unavailable: Optional[str] = None,
) -> Dict[str, str]:
    """
    Pure routing policy. Returns provider/model/effort/risk/route_reason.
    - Unspecified risk fails safe to 'critical'; invalid risk is rejected.
    - Critical implementation: Claude Sonnet 5.5 medium. ChatGPT Luna medium ONLY when the
      operator (or persisted provider health) states Claude is unavailable, with the reason
      recorded. This is an explicit decision, not automatic quota failover; no paid API.
    - Flash is allowed only for routine risk. Argon only for research. Anything outside
      the catalog is rejected.
    """
    if kind not in KINDS:
        raise RoutingError(f"Unknown job kind '{kind}'; expected one of {KINDS}")
    notes: List[str] = []
    if risk is None or not str(risk).strip():
        risk = "critical"
        notes.append("risk unspecified: failed safe to critical")
    elif risk not in RISKS:
        raise RoutingError(f"Unknown risk '{risk}'; expected one of {RISKS}")

    requested = None
    if override and any(override):
        if not all(override):
            raise RoutingError("Override requires provider, model, and effort together")
        requested = tuple(override)
        notes.append("explicit operator override (must equal the policy-selected route)")
    if kind == "review":
        key = "sol"
    elif kind in ("research", "planning"):
        # Ordered: Opus medium -> Sol medium (user-authorized Opus substitute) -> Argon low.
        # Each step down needs a stated unavailability reason; Argon is never a silent default.
        if not (claude_unavailable and claude_unavailable.strip()):
            key = "opus"
        elif not (codex_unavailable and codex_unavailable.strip()):
            key = "sol_med"
            notes.append(f"Opus unavailable ({sanitize_error_message(claude_unavailable.strip())}); Sol medium substitutes")
        else:
            key = "argon"
            notes.append(
                f"Opus unavailable ({sanitize_error_message(claude_unavailable.strip())}) and "
                f"Sol unavailable ({sanitize_error_message(codex_unavailable.strip())}); Argon low last resort"
            )
    elif risk == "routine":
        key = "flash"
    elif claude_unavailable and claude_unavailable.strip():
        key = "luna"
        notes.append(
            f"FALLBACK to ChatGPT: Claude declared unavailable ({sanitize_error_message(claude_unavailable.strip())}); "
            "explicit decision, not automatic failover; subscription only, no paid API"
        )
    else:
        key = "sonnet"

    if requested is not None and requested != MODEL_CATALOG[key]:
        raise RoutingError(
            f"Override {requested} does not match the route selected by policy for "
            f"{kind}/{risk} with the stated availability: {MODEL_CATALOG[key]}"
        )
    if key == "flash" and risk != "routine":
        raise RoutingError("Gemini Flash is not permitted for critical or unspecified-risk jobs")
    if key == "argon" and kind not in ("research", "planning"):
        raise RoutingError("Gemini Argon is only permitted for research/planning jobs")
    if key in ("opus", "sol_med") and kind not in ("research", "planning"):
        raise RoutingError("Opus/Sol-medium routes are for research/planning jobs")
    provider, model, effort = MODEL_CATALOG[key]
    reason = f"{kind}/{risk} -> {key}" + (": " + "; ".join(notes) if notes else "")
    return {"provider": provider, "model": model, "effort": effort, "risk": risk, "route_reason": reason}

def resolve_target_agent(target: str) -> Tuple[str, Optional[Dict[str, str]]]:
    """Resolves target name or agent_id to (agent_id, specialist_metadata)."""
    target_clean = target.strip().lower()
    if target_clean in SPECIALISTS:
        return SPECIALISTS[target_clean]["agent_id"], SPECIALISTS[target_clean]
    for name, spec in SPECIALISTS.items():
        if spec["agent_id"] == target.strip():
            return spec["agent_id"], spec
    return target.strip(), None

def sanitize_error_message(msg: Any) -> str:
    """Strips sensitive tokens, bearer credentials, and keys from error messages."""
    text = str(msg)
    redacted = re.sub(r"(?i)bearer\s+[A-Za-z0-9_\-\.~+/=]+", "Bearer [REDACTED]", text)
    redacted = re.sub(
        r"(?i)(token|secret|api[_-]?key|key|password)([\"']?\s*[=:]\s*|\s+)[\"']?[^\s\"',}]+",
        r"\1=[REDACTED]",
        redacted,
    )
    redacted = re.sub(r"\b(sk|ghp|xox[bap])-?[A-Za-z0-9_\-]{16,}", "[REDACTED]", redacted)
    return redacted

def generate_send_id() -> str:
    """Generates a CUID2-compliant identifier: ^[a-z][a-z0-9]+$ (2-96 chars)."""
    return "m" + secrets.token_hex(16)

def current_iso_time() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class DispatchError(Exception):
    """Base error for dispatch operations."""

class PayloadConflictError(DispatchError):
    """Raised when submitting an existing job ID with conflicting payload."""

class JobNotFoundError(DispatchError):
    """Raised when job does not exist."""

class AdmissionError(DispatchError):
    """Raised when job admission fails."""

class InvalidStateError(DispatchError):
    """Raised on invalid lifecycle transitions."""

class AuthenticationError(DispatchError):
    """Raised on authentication failures."""

class PreflightError(DispatchError):
    """Raised on capability or readiness preflight failures."""

class AgentBusyError(PreflightError):
    """Target agent is not idle. A read-only observation, not counted as a failure."""

class LiveMutationDisabledError(DispatchError):
    """Live sends/aborts are globally disabled on the real transport (integration deferred)."""

class SendRejectedError(DispatchError):
    """Daemon definitively rejected the send (400/404/409): no message was created."""

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class Job:
    id: str
    owner: str
    target_agent: str
    provider: str
    model: str
    effort: str
    objective: str
    inputs: str
    provenance: Optional[str] = None
    acceptance_checks: Optional[str] = None
    eta_minutes: int = 15
    status: str = "queued"  # queued, reserved, sending, running, completed, blocked, cancelled, cancel_pending
    send_id: Optional[str] = None
    attempt_count: int = 0
    max_attempts: int = 2
    last_error: Optional[str] = None
    last_error_cause: Optional[str] = None
    consecutive_same_cause_failures: int = 0
    evidence: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    admitted_at: Optional[str] = None
    completed_at: Optional[str] = None
    payload_hash: str = ""
    kind: str = "implementation"
    risk: str = "critical"
    route_reason: str = ""
    run_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Job:
        return cls(
            id=row["id"],
            owner=row["owner"],
            target_agent=row["target_agent"],
            provider=row["provider"],
            model=row["model"],
            effort=row["effort"],
            objective=row["objective"],
            inputs=row["inputs"],
            provenance=row["provenance"],
            acceptance_checks=row["acceptance_checks"],
            eta_minutes=row["eta_minutes"],
            status=row["status"],
            send_id=row["send_id"],
            attempt_count=row["attempt_count"],
            max_attempts=row["max_attempts"],
            last_error=row["last_error"],
            last_error_cause=row["last_error_cause"],
            consecutive_same_cause_failures=row["consecutive_same_cause_failures"],
            evidence=row["evidence"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            admitted_at=row["admitted_at"],
            completed_at=row["completed_at"],
            payload_hash=row["payload_hash"],
            kind=row["kind"],
            risk=row["risk"],
            route_reason=row["route_reason"],
            run_id=row["run_id"],
        )

def compute_payload_hash(payload: Dict[str, Any]) -> str:
    canonical = {
        "owner": payload.get("owner", ""),
        "target_agent": payload.get("target_agent", ""),
        "provider": payload.get("provider", ""),
        "model": payload.get("model", ""),
        "effort": payload.get("effort", ""),
        "objective": payload.get("objective", ""),
        "inputs": payload.get("inputs", ""),
        "provenance": payload.get("provenance") or "",
        "acceptance_checks": payload.get("acceptance_checks") or "",
        "kind": payload.get("kind", "implementation"),
        "risk": payload.get("risk", "critical"),
    }
    encoded = json.dumps(canonical, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

# ---------------------------------------------------------------------------
# Durable SQLite Job Ledger
# ---------------------------------------------------------------------------

class JobLedger:
    """
    Durable SQLite ledger providing atomic two-worker admission across processes,
    per-target-agent exclusivity, state transitions, provider health tracking,
    and audit event logs.
    """

    def __init__(self, db_path: pathlib.Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            isolation_level=None,  # Manual autocommit/explicit transactions
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    target_agent TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    effort TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    inputs TEXT NOT NULL,
                    provenance TEXT,
                    acceptance_checks TEXT,
                    eta_minutes INTEGER NOT NULL DEFAULT 15,
                    status TEXT NOT NULL,
                    send_id TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 2,
                    last_error TEXT,
                    last_error_cause TEXT,
                    consecutive_same_cause_failures INTEGER NOT NULL DEFAULT 0,
                    evidence TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    admitted_at TEXT,
                    completed_at TEXT,
                    payload_hash TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'implementation',
                    risk TEXT NOT NULL DEFAULT 'critical',
                    route_reason TEXT NOT NULL DEFAULT '',
                    run_id TEXT
                )
            """)
            existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}
            for col, ddl in (
                ("kind", "TEXT NOT NULL DEFAULT 'implementation'"),
                ("risk", "TEXT NOT NULL DEFAULT 'critical'"),
                ("route_reason", "TEXT NOT NULL DEFAULT ''"),
                ("run_id", "TEXT"),
            ):
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {ddl}")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS job_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES jobs(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS provider_health (
                    provider TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    last_error TEXT,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_target ON jobs(target_agent)")

    def is_provider_blocked(self, provider: str) -> Tuple[bool, Optional[str]]:
        """Checks if a provider has been blocked by an authentication failure."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status, last_error FROM provider_health WHERE provider = ?",
                (provider,)
            )
            row = cursor.fetchone()
            if row and row["status"] == "blocked":
                return True, row["last_error"]
            return False, None

    def set_provider_blocked(self, provider: str, error_msg: str) -> None:
        """Sets a provider to blocked state across all jobs."""
        now_iso = current_iso_time()
        sanitized = sanitize_error_message(error_msg)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO provider_health (provider, status, last_error, updated_at)
                VALUES (?, 'blocked', ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    status = 'blocked',
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
            """, (provider, sanitized, now_iso))

    def unblock_provider(self, provider: str) -> None:
        """Restores a provider's health to active."""
        now_iso = current_iso_time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO provider_health (provider, status, last_error, updated_at)
                VALUES (?, 'active', NULL, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    status = 'active',
                    last_error = NULL,
                    updated_at = excluded.updated_at
            """, (provider, now_iso))

    def submit_job(self, job_dict: Dict[str, Any]) -> Job:
        """Submits a job. Idempotent for identical payload; rejects conflicting payload under same ID."""
        job_id = job_dict["id"]
        payload_hash = compute_payload_hash(job_dict)
        now_iso = current_iso_time()

        conn = self._get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            existing = cursor.fetchone()
            if existing:
                existing_job = Job.from_row(existing)
                if existing_job.payload_hash == payload_hash:
                    conn.execute("COMMIT")
                    return existing_job
                conn.execute("ROLLBACK")
                raise PayloadConflictError(
                    f"Job {job_id} already exists with a different payload. "
                    f"Existing hash: {existing_job.payload_hash[:8]}, new hash: {payload_hash[:8]}."
                )

            cursor.execute("""
                INSERT INTO jobs (
                    id, owner, target_agent, provider, model, effort,
                    objective, inputs, provenance, acceptance_checks, eta_minutes,
                    status, send_id, attempt_count, max_attempts,
                    created_at, updated_at, payload_hash, kind, risk, route_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', NULL, 0, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id,
                job_dict["owner"],
                job_dict["target_agent"],
                job_dict["provider"],
                job_dict["model"],
                job_dict["effort"],
                job_dict["objective"],
                job_dict["inputs"],
                job_dict.get("provenance"),
                job_dict.get("acceptance_checks"),
                job_dict.get("eta_minutes", 15),
                job_dict.get("max_attempts", 2),
                now_iso,
                now_iso,
                payload_hash,
                job_dict.get("kind", "implementation"),
                job_dict.get("risk", "critical"),
                job_dict.get("route_reason", ""),
            ))
            cursor.execute("""
                INSERT INTO job_events (job_id, event_type, payload, created_at)
                VALUES (?, 'submit', ?, ?)
            """, (job_id, json.dumps({
                "owner": job_dict["owner"],
                "kind": job_dict.get("kind", "implementation"),
                "risk": job_dict.get("risk", "critical"),
                "route": [job_dict["provider"], job_dict["model"], job_dict["effort"]],
                "route_reason": job_dict.get("route_reason", ""),
            }), now_iso))
            conn.execute("COMMIT")

            return self.get_job(job_id)
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def get_job(self, job_id: str) -> Job:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            if not row:
                raise JobNotFoundError(f"Job {job_id} not found in ledger")
            return Job.from_row(row)

    def list_jobs(self, status: Optional[str] = None) -> List[Job]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM jobs WHERE status = ? ORDER BY created_at ASC", (status,))
            else:
                cursor.execute("SELECT * FROM jobs ORDER BY created_at ASC")
            return [Job.from_row(r) for r in cursor.fetchall()]

    def get_events(self, job_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT event_id, event_type, payload, created_at FROM job_events WHERE job_id = ? ORDER BY event_id ASC",
                (job_id,)
            )
            events = []
            for r in cursor.fetchall():
                payload = json.loads(r["payload"]) if r["payload"] else None
                events.append({
                    "event_id": r["event_id"],
                    "event_type": r["event_type"],
                    "payload": payload,
                    "created_at": r["created_at"],
                })
            return events

    def can_admit(self, job_id: str) -> Tuple[bool, str]:
        """Non-mutating admission feasibility check (used for dry-run preview)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM jobs WHERE status IN ('reserved', 'sending', 'running', 'cancel_pending')"
            )
            active_count = cursor.fetchone()[0]
            if active_count >= 2:
                return False, "Global active worker limit reached (2 active jobs)"

            cursor.execute(
                "SELECT target_agent, status, provider, attempt_count, max_attempts, consecutive_same_cause_failures FROM jobs WHERE id = ?",
                (job_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False, f"Job {job_id} not found"
            if row["status"] != "queued":
                return False, f"Job {job_id} is in status '{row['status']}', expected 'queued'"

            # Provider health check
            blocked, err = self.is_provider_blocked(row["provider"])
            if blocked:
                return False, f"Provider '{row['provider']}' is blocked due to authentication failure: {err}"

            if row["consecutive_same_cause_failures"] >= 2 or row["attempt_count"] >= row["max_attempts"]:
                return False, f"Job {job_id} has exhausted attempt budget or reached 2 same-cause failures"

            cursor.execute(
                "SELECT COUNT(*) FROM jobs WHERE target_agent = ? AND status IN ('reserved', 'sending', 'running', 'cancel_pending')",
                (row["target_agent"],)
            )
            if cursor.fetchone()[0] > 0:
                return False, f"Target agent {row['target_agent']} already has an active reservation or worker"

            return True, "Ready for admission"

    def admit_job(self, job_id: str) -> Optional[Job]:
        """
        Atomically admits a queued job if:
          1. Global active workers < 2 (active statuses: reserved, sending, running, cancel_pending).
          2. Target agent has 0 active workers (per-agent exclusivity).
          3. Target provider is not blocked by auth failures.
        Returns the admitted Job in status 'reserved' with an assigned send_id,
        or None if limits prevent admission.
        """
        now_iso = current_iso_time()
        conn = self._get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()

            # 1. Check global concurrency limit
            cursor.execute(
                "SELECT COUNT(*) FROM jobs WHERE status IN ('reserved', 'sending', 'running', 'cancel_pending')"
            )
            active_count = cursor.fetchone()[0]
            if active_count >= 2:
                conn.execute("COMMIT")
                return None

            # 2. Check candidate job
            cursor.execute(
                "SELECT target_agent, status, provider, attempt_count, max_attempts, send_id, consecutive_same_cause_failures FROM jobs WHERE id = ?",
                (job_id,)
            )
            row = cursor.fetchone()
            if not row:
                conn.execute("COMMIT")
                raise JobNotFoundError(f"Job {job_id} not found")

            target_agent = row["target_agent"]
            status = row["status"]
            provider = row["provider"]
            attempt_count = row["attempt_count"]
            max_attempts = row["max_attempts"]
            send_id = row["send_id"]
            same_cause_failures = row["consecutive_same_cause_failures"]

            if status != "queued":
                conn.execute("COMMIT")
                return None

            # Check provider health
            cursor.execute(
                "SELECT status, last_error FROM provider_health WHERE provider = ?",
                (provider,)
            )
            p_health = cursor.fetchone()
            if p_health and p_health["status"] == "blocked":
                # Provider is temporarily blocked by auth failure. Reject admission while provider is blocked.
                conn.execute("COMMIT")
                return None

            if same_cause_failures >= 2 or attempt_count >= max_attempts:
                cursor.execute(
                    "UPDATE jobs SET status = 'blocked', updated_at = ? WHERE id = ?",
                    (now_iso, job_id)
                )
                cursor.execute(
                    "INSERT INTO job_events (job_id, event_type, payload, created_at) VALUES (?, 'blocked', ?, ?)",
                    (job_id, json.dumps({"reason": "Max attempts or consecutive failures reached"}), now_iso)
                )
                conn.execute("COMMIT")
                return None

            # 3. Check target agent exclusivity
            cursor.execute(
                "SELECT COUNT(*) FROM jobs WHERE target_agent = ? AND status IN ('reserved', 'sending', 'running', 'cancel_pending')",
                (target_agent,)
            )
            target_active = cursor.fetchone()[0]
            if target_active > 0:
                conn.execute("COMMIT")
                return None

            # 4. Perform atomic state transition to 'reserved'
            assigned_send_id = send_id if send_id else generate_send_id()
            cursor.execute("""
                UPDATE jobs
                SET status = 'reserved',
                    send_id = ?,
                    attempt_count = attempt_count + 1,
                    admitted_at = ?,
                    updated_at = ?
                WHERE id = ? AND status = 'queued'
            """, (assigned_send_id, now_iso, now_iso, job_id))

            if cursor.rowcount == 0:
                conn.execute("COMMIT")
                return None

            cursor.execute("SELECT provider, model, effort, risk, route_reason FROM jobs WHERE id = ?", (job_id,))
            pins = cursor.fetchone()
            cursor.execute("""
                INSERT INTO job_events (job_id, event_type, payload, created_at)
                VALUES (?, 'admit', ?, ?)
            """, (job_id, json.dumps({
                "attempt": attempt_count + 1,
                "send_id": assigned_send_id,
                "pinned": [pins["provider"], pins["model"], pins["effort"]],
                "risk": pins["risk"],
                "route_reason": pins["route_reason"],
            }), now_iso))

            conn.execute("COMMIT")
            return self.get_job(job_id)
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def claim_for_send(self, job_id: str) -> bool:
        """
        Compare-and-swap claim: transitions status 'reserved' -> 'sending'.
        Guarantees that if the job was cancelled during preflight,
        the sender CANNOT transmit bytes!
        """
        now_iso = current_iso_time()
        conn = self._get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE jobs SET status = 'sending', updated_at = ? WHERE id = ? AND status = 'reserved'",
                (now_iso, job_id)
            )
            claimed = cursor.rowcount > 0
            if claimed:
                cursor.execute("""
                    INSERT INTO job_events (job_id, event_type, payload, created_at)
                    VALUES (?, 'send_claim', ?, ?)
                """, (job_id, json.dumps({"status": "sending"}), now_iso))
            conn.execute("COMMIT")
            return claimed
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def release_reservation_to_queued(self, job_id: str, reason: str, is_capability_mismatch: bool = False) -> Job:
        """
        Releases a reservation back to queued before send.
        If is_capability_mismatch is True, counts as a failure against 2-strike limit.
        """
        now_iso = current_iso_time()
        sanitized_reason = sanitize_error_message(reason)
        conn = self._get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status, attempt_count, consecutive_same_cause_failures, last_error_cause FROM jobs WHERE id = ?",
                (job_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise JobNotFoundError(f"Job {job_id} not found")
            if row["status"] not in ("reserved", "sending"):
                raise InvalidStateError(f"Cannot revert non-reserved job {job_id} (status: {row['status']})")

            consecutive = row["consecutive_same_cause_failures"]
            new_consecutive = (consecutive + 1) if (row["last_error_cause"] == "preflight_capability") else 1

            if is_capability_mismatch:
                should_block = (new_consecutive >= 2)
                new_status = "blocked" if should_block else "queued"
                cursor.execute("""
                    UPDATE jobs
                    SET status = ?,
                        last_error = ?,
                        last_error_cause = 'preflight_capability',
                        consecutive_same_cause_failures = ?,
                        updated_at = ?
                    WHERE id = ? AND status IN ('reserved', 'sending')
                """, (new_status, sanitized_reason, new_consecutive, now_iso, job_id))
            else:
                # Transient preflight pause (e.g. agent busy) - roll back attempt count
                new_attempts = max(0, row["attempt_count"] - 1)
                cursor.execute("""
                    UPDATE jobs
                    SET status = 'queued',
                        attempt_count = ?,
                        last_error = ?,
                        updated_at = ?
                    WHERE id = ? AND status IN ('reserved', 'sending')
                """, (new_attempts, sanitized_reason, now_iso, job_id))

            cursor.execute("""
                INSERT INTO job_events (job_id, event_type, payload, created_at)
                VALUES (?, 'reservation_released', ?, ?)
            """, (job_id, json.dumps({"reason": sanitized_reason, "capability_mismatch": is_capability_mismatch}), now_iso))
            conn.execute("COMMIT")
            return self.get_job(job_id)
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def mark_running(self, job_id: str, run_id: Optional[str] = None) -> Job:
        """Transitions job from 'sending' to 'running' after verified send; stores the run ID if known."""
        now_iso = current_iso_time()
        conn = self._get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            if not row:
                raise JobNotFoundError(f"Job {job_id} not found")

            if run_id and row["status"] in ("sending", "reserved", "cancel_pending"):
                cursor.execute("UPDATE jobs SET run_id = ? WHERE id = ?", (run_id, job_id))
            if row["status"] == "cancel_pending":
                # Cancellation was requested while sending. Slot remains held in cancel_pending!
                conn.execute("COMMIT")
                return self.get_job(job_id)

            if row["status"] not in ("sending", "reserved"):
                raise InvalidStateError(f"Cannot mark job {job_id} as running from status '{row['status']}'")

            cursor.execute("""
                UPDATE jobs
                SET status = 'running', updated_at = ?
                WHERE id = ? AND status IN ('sending', 'reserved')
            """, (now_iso, job_id))

            cursor.execute("""
                INSERT INTO job_events (job_id, event_type, payload, created_at)
                VALUES (?, 'running', ?, ?)
            """, (job_id, json.dumps({"timestamp": now_iso}), now_iso))
            conn.execute("COMMIT")
            return self.get_job(job_id)
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def record_ambiguous_send(self, job_id: str, error_msg: str) -> Job:
        """
        Records an ambiguous send outcome (e.g. timeout or connection drop).
        CRITICAL: The job status transitions back to 'reserved' and the slot is HELD.
        No automatic retry with a new send_id is performed.
        """
        now_iso = current_iso_time()
        sanitized_err = sanitize_error_message(error_msg)

        conn = self._get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            if not row:
                raise JobNotFoundError(f"Job {job_id} not found")

            if row["status"] in ("cancelled", "completed", "blocked", "queued"):
                # Terminal/released by operator attestation while send was in flight: do not
                # resurrect or re-occupy a slot; keep the audit trail of the unknown outcome.
                new_status = row["status"]
                cursor.execute("""
                    INSERT INTO job_events (job_id, event_type, payload, created_at)
                    VALUES (?, 'send_ambiguous_after_release', ?, ?)
                """, (job_id, json.dumps({"error": sanitized_err, "status": new_status}), now_iso))
                conn.execute("COMMIT")
                return self.get_job(job_id)
            new_status = "cancel_pending" if row["status"] == "cancel_pending" else "reserved"

            cursor.execute("""
                UPDATE jobs
                SET status = ?,
                    last_error = ?,
                    last_error_cause = 'ambiguous_transport',
                    updated_at = ?
                WHERE id = ?
            """, (new_status, sanitized_err, now_iso, job_id))

            cursor.execute("""
                INSERT INTO job_events (job_id, event_type, payload, created_at)
                VALUES (?, 'send_ambiguous', ?, ?)
            """, (job_id, json.dumps({"error": sanitized_err, "status": new_status}), now_iso))
            conn.execute("COMMIT")
            return self.get_job(job_id)
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def record_failure_and_maybe_block(
        self, job_id: str, cause: str, error_msg: str, definite_pre_send: bool = False
    ) -> Job:
        """
        Records a normalized failure cause.
        - If cause is 'auth': blocks job AND sets provider health to blocked.
        - If 2 consecutive same-cause failures: moves job to 'blocked'.
        - If definite_pre_send is True: releases the slot immediately (status -> queued or blocked).
        - If NOT definite_pre_send: keeps slot in 'reserved' or 'blocked' (holds slot if ambiguous).
        """
        now_iso = current_iso_time()
        sanitized_err = sanitize_error_message(error_msg)

        conn = self._get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            cursor.execute("""
                SELECT status, provider, attempt_count, max_attempts, last_error_cause,
                       consecutive_same_cause_failures
                FROM jobs WHERE id = ?
            """, (job_id,))
            row = cursor.fetchone()
            if not row:
                raise JobNotFoundError(f"Job {job_id} not found")

            status = row["status"]
            provider = row["provider"]
            last_cause = row["last_error_cause"]
            consecutive = row["consecutive_same_cause_failures"]
            attempt_count = row["attempt_count"]
            max_attempts = row["max_attempts"]

            new_consecutive = (consecutive + 1) if (last_cause == cause) else 1
            is_auth = (cause == "auth")
            should_block = is_auth or (new_consecutive >= 2) or (attempt_count >= max_attempts)

            if is_auth:
                # Update provider health table
                cursor.execute("""
                    INSERT INTO provider_health (provider, status, last_error, updated_at)
                    VALUES (?, 'blocked', ?, ?)
                    ON CONFLICT(provider) DO UPDATE SET
                        status = 'blocked',
                        last_error = excluded.last_error,
                        updated_at = excluded.updated_at
                """, (provider, sanitized_err, now_iso))

            if not definite_pre_send:
                new_status = status  # possibly executing: slot is never freed here
            elif should_block:
                new_status = "blocked"
            else:
                new_status = "queued"

            cursor.execute("""
                UPDATE jobs
                SET status = ?,
                    last_error = ?,
                    last_error_cause = ?,
                    consecutive_same_cause_failures = ?,
                    updated_at = ?
                WHERE id = ?
            """, (new_status, sanitized_err, cause, new_consecutive, now_iso, job_id))

            cursor.execute("""
                INSERT INTO job_events (job_id, event_type, payload, created_at)
                VALUES (?, 'failure', ?, ?)
            """, (job_id, json.dumps({
                "cause": cause,
                "consecutive": new_consecutive,
                "status": new_status,
                "error": sanitized_err,
            }), now_iso))

            conn.execute("COMMIT")
            return self.get_job(job_id)
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def complete_job(
        self,
        job_id: str,
        result_evidence: str,
        stopped_attestation: Optional[str] = None,
    ) -> Job:
        """
        Completes a running job.
        Requires BOTH:
          1. result_evidence: non-empty verified results.
          2. stopped proof: an explicit stopped_attestation (idle status alone is not proof).
        Idempotent on already completed jobs.
        """
        if not result_evidence or not result_evidence.strip():
            raise ValueError("Completion requires verified result evidence.")

        now_iso = current_iso_time()
        conn = self._get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            cursor.execute("SELECT status, target_agent, evidence, attempt_count, send_id FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            if not row:
                raise JobNotFoundError(f"Job {job_id} not found")

            if row["status"] == "completed":
                conn.execute("COMMIT")
                return self.get_job(job_id)

            if row["status"] not in ("running", "reserved", "cancel_pending"):
                raise InvalidStateError(
                    f"Cannot complete job {job_id} in state '{row['status']}'. "
                    f"Must be 'running', 'reserved', 'sending', or 'cancel_pending'."
                )

            # Check stopped evidence
            has_stopped_proof = False
            stopped_note = ""
            if stopped_attestation and stopped_attestation.strip():
                has_stopped_proof = True
                stopped_note = stopped_attestation.strip()

            if not has_stopped_proof:
                raise InvalidStateError(
                    "Worker termination evidence required to release slot. "
                    "Provide an explicit --stopped-attestation (idle status alone does not prove "
                    "this job's message finished)."
                )

            combined_evidence = f"Results: {result_evidence.strip()} | Stopped Proof: {stopped_note}"

            cursor.execute("""
                UPDATE jobs
                SET status = 'completed',
                    evidence = ?,
                    completed_at = ?,
                    updated_at = ?
                WHERE id = ?
            """, (combined_evidence, now_iso, now_iso, job_id))

            cursor.execute("""
                INSERT INTO job_events (job_id, event_type, payload, created_at)
                VALUES (?, 'completed', ?, ?)
            """, (job_id, json.dumps({
                "attempt": row["attempt_count"],
                "send_id": row["send_id"],
                "stopped_proof": stopped_note,
            }), now_iso))

            conn.execute("COMMIT")
            return self.get_job(job_id)
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def cancel_job(
        self,
        job_id: str,
        stopped_attestation: Optional[str] = None,
    ) -> Job:
        """
        Cancels a job:
        - Queued jobs: immediate transition to 'cancelled'. Slot released.
        - Reserved/sending/running jobs:
          - If an explicit stopped_attestation is given (idle status alone is NOT proof): transition to 'cancelled'. Slot released.
          - Otherwise: enters 'cancel_pending'. Slot REMAINS OCCUPIED until stopped proof provided.
        - Already cancelled jobs: idempotent return.
        """
        now_iso = current_iso_time()
        conn = self._get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            cursor.execute("SELECT status, target_agent FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            if not row:
                raise JobNotFoundError(f"Job {job_id} not found")

            current_status = row["status"]
            if current_status == "cancelled":
                conn.execute("COMMIT")
                return self.get_job(job_id)

            if current_status == "completed":
                raise InvalidStateError(f"Cannot cancel already completed job {job_id}")
            if current_status == "sending":
                raise InvalidStateError(f"Cannot cancel job {job_id} while a send is in progress")

            if current_status == "queued":
                cursor.execute("""
                    UPDATE jobs SET status = 'cancelled', updated_at = ? WHERE id = ?
                """, (now_iso, job_id))
                cursor.execute("""
                    INSERT INTO job_events (job_id, event_type, payload, created_at)
                    VALUES (?, 'cancelled', ?, ?)
                """, (job_id, json.dumps({"from": "queued"}), now_iso))
                conn.execute("COMMIT")
                return self.get_job(job_id)

            # Check stopped evidence
            has_stop_evidence = False
            evidence_text = ""
            if stopped_attestation and stopped_attestation.strip():
                has_stop_evidence = True
                evidence_text = stopped_attestation.strip()

            if has_stop_evidence:
                cursor.execute("""
                    UPDATE jobs
                    SET status = 'cancelled',
                        evidence = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (evidence_text, now_iso, job_id))
                cursor.execute("""
                    INSERT INTO job_events (job_id, event_type, payload, created_at)
                    VALUES (?, 'cancelled', ?, ?)
                """, (job_id, json.dumps({"stopped_evidence": evidence_text}), now_iso))
            else:
                cursor.execute("""
                    UPDATE jobs
                    SET status = 'cancel_pending',
                        updated_at = ?
                    WHERE id = ?
                """, (now_iso, job_id))
                cursor.execute("""
                    INSERT INTO job_events (job_id, event_type, payload, created_at)
                    VALUES (?, 'cancel_pending', ?, ?)
                """, (job_id, json.dumps({"notice": "Slot held until stopped proof provided"}), now_iso))

            conn.execute("COMMIT")
            return self.get_job(job_id)
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def reconcile_job(self, job_id: str, action: str, evidence: str) -> Job:
        """
        Explicit reconciliation for ambiguous, cancel_pending, or blocked jobs.
        Actions:
          - 'confirm_running': verifies message was accepted and moves reserved -> running.
          - 'confirm_stopped': moves cancel_pending/reserved -> cancelled (releases slot).
          - 'unblock': resets blocked status -> queued, authoring a fresh attempt budget (attempt_count = 0).
        """
        if not evidence or not evidence.strip():
            raise ValueError("Reconciliation requires explicit auditable evidence.")

        now_iso = current_iso_time()
        sanitized_ev = sanitize_error_message(evidence)

        conn = self._get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            cursor.execute("SELECT status, target_agent FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            if not row:
                raise JobNotFoundError(f"Job {job_id} not found")

            curr_status = row["status"]
            if action == "confirm_running":
                if curr_status != "reserved":
                    raise InvalidStateError(f"Cannot confirm running for job in status {curr_status}")
                cursor.execute(
                    "UPDATE jobs SET status = 'running', updated_at = ? WHERE id = ?",
                    (now_iso, job_id)
                )
            elif action == "confirm_stopped":
                if curr_status not in ("reserved", "running", "cancel_pending", "blocked"):
                    raise InvalidStateError(f"Cannot confirm stopped for job in status {curr_status}")
                cursor.execute(
                    "UPDATE jobs SET status = 'cancelled', evidence = ?, updated_at = ? WHERE id = ?",
                    (sanitized_ev, now_iso, job_id)
                )
            elif action == "unblock":
                if curr_status != "blocked":
                    raise InvalidStateError(f"Cannot unblock job in status {curr_status}")
                # Reset attempt counters and failure counts for fresh budget
                cursor.execute("""
                    UPDATE jobs
                    SET status = 'queued',
                        attempt_count = 0,
                        consecutive_same_cause_failures = 0,
                        last_error = NULL,
                        last_error_cause = NULL,
                        updated_at = ?
                    WHERE id = ?
                """, (now_iso, job_id))
            else:
                raise ValueError(f"Unknown reconciliation action: {action}")

            cursor.execute("""
                INSERT INTO job_events (job_id, event_type, payload, created_at)
                VALUES (?, 'reconcile', ?, ?)
            """, (job_id, json.dumps({"action": action, "evidence": sanitized_ev}), now_iso))

            conn.execute("COMMIT")
            return self.get_job(job_id)
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            conn.close()

# ---------------------------------------------------------------------------
# Compact Handoff Renderer
# ---------------------------------------------------------------------------

class HandoffRenderer:
    """Renders compact, token-efficient assignment handoffs with scientific provenance."""

    @staticmethod
    def render(job: Job) -> str:
        lines = [
            f"# Assignment Handoff: {job.id}",
            f"**Target Agent:** `{job.target_agent}`",
            f"**Pinned Model / Effort:** `{job.provider}` / `{job.model}` ({job.effort})",
            f"**Owner Agent:** `{job.owner}`",
            f"**Time Budget / ETA:** {job.eta_minutes} minutes",
            "",
            "## 1. Objective & Scientific Claim",
            job.objective.strip(),
            "",
            "## 2. Explicit Inputs & Assigned References",
            job.inputs.strip(),
            "",
            "## 3. Provenance & Reproducibility Assumptions",
            (job.provenance.strip() if job.provenance else "Not supplied; do not infer provenance or scientific assumptions."),
            "",
            "## 4. Acceptance & Verification Checks",
            (job.acceptance_checks.strip() if job.acceptance_checks else "Report verified output and test results verbatim."),
            "",
            "## 5. Protocol Boundaries",
            "- Changes to statistical methods, data exclusions, numerical results, or conclusions require independent review AND the user's decision; reviewer approval is not user approval.",
            "- Pinned model selection is immutable. No automatic cross-provider fallback.",
            f"- On completion, submit findings and report Job ID `{job.id}`.",
        ]
        return "\n".join(lines)

# ---------------------------------------------------------------------------
# Happy Local API Transport Seam
# ---------------------------------------------------------------------------

class Transport(Protocol):
    def request(
        self, method: str, path: str, headers: Dict[str, str], body: Optional[Dict[str, Any]] = None
    ) -> Tuple[int, Dict[str, Any]]:
        ...

class UnixHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection over Unix domain socket using standard library framing."""

    def __init__(self, socket_path: pathlib.Path, timeout: float = 10.0):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        try:
            self.sock.connect(str(self.socket_path))
        except PermissionError as e:
            raise PreflightError(
                f"Transport connection refused by sandbox (host socket permission required): {e}"
            )
        except Exception as e:
            raise PreflightError(f"Failed to connect to Happy socket {self.socket_path}: {e}")

class UnixSocketTransport:
    """Standard-library HTTP/1.1 transport over macOS/Linux Unix domain socket."""

    def __init__(self, socket_path: pathlib.Path, token_path: pathlib.Path, timeout: float = 10.0):
        self.socket_path = socket_path
        self.token_path = token_path
        self.timeout = timeout

    def _read_token(self) -> str:
        env_token = os.environ.get("HAPPY_TOKEN")
        if env_token:
            return env_token.strip()
        if not self.token_path.exists():
            raise AuthenticationError(f"Happy token file not found at {self.token_path}")
        try:
            return self.token_path.read_text("utf-8").strip()
        except Exception as e:
            raise AuthenticationError(f"Unable to read Happy token: {e}")

    def request(
        self, method: str, path: str, headers: Dict[str, str], body: Optional[Dict[str, Any]] = None
    ) -> Tuple[int, Dict[str, Any]]:
        token = self._read_token()
        req_headers = dict(headers)
        req_headers["Authorization"] = f"Bearer {token}"
        req_headers["Host"] = "localhost"

        payload_bytes = None
        if body is not None:
            payload_bytes = json.dumps(body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
            req_headers["Content-Length"] = str(len(payload_bytes))

        conn = UnixHTTPConnection(self.socket_path, timeout=self.timeout)
        try:
            conn.request(method, path, body=payload_bytes, headers=req_headers)
            resp = conn.getresponse()
            status_code = resp.status
            raw_data = resp.read()
            resp_json = json.loads(raw_data.decode("utf-8")) if raw_data else {}
            return status_code, resp_json
        finally:
            conn.close()

class FakeTransport:
    """In-memory test fake supporting injection of responses, errors, and agent metadata."""

    def __init__(self):
        self.agents: Dict[str, Dict[str, Any]] = {}
        self.modes: Dict[str, Dict[str, Any]] = {}
        self.received_messages: List[Dict[str, Any]] = []
        self.aborted_agents: List[str] = []
        self.allows_live_mutation = True  # test-only fake; the real transport lacks this attribute
        self.abort_bodies: List[Dict[str, Any]] = []
        self.run_ids: Dict[str, str] = {}
        self.active_run: Dict[str, str] = {}
        self.fail_send_with: Optional[Exception] = None
        self.fail_auth: bool = False
        self.fail_mode_auth: bool = False
        self.fail_mode_status: Optional[int] = None
        self.on_preflight_hook: Optional[Callable[[], None]] = None

    def set_agent(self, agent_id: str, status: str = "idle"):
        self.agents[agent_id] = {
            "id": agent_id,
            "status": status,
        }

    def set_mode(self, agent_id: str, provider: str, model: str, effort: str):
        self.modes[agent_id] = {
            "mode": {
                "providerId": provider,
                "modelId": model,
                "effort": effort,
                "serviceTier": None,
                "permissionMode": "auto",
            }
        }

    def request(
        self, method: str, path: str, headers: Dict[str, str], body: Optional[Dict[str, Any]] = None
    ) -> Tuple[int, Dict[str, Any]]:
        if self.fail_auth:
            return 401, {"error": "unauthorized"}

        if self.fail_send_with and "/send" in path:
            exc = self.fail_send_with
            self.fail_send_with = None
            raise exc

        if method == "GET" and path.startswith("/v0/agents/") and path.endswith("/mode"):
            if self.fail_mode_auth:
                return 401, {"error": "unauthorized"}
            if self.fail_mode_status:
                return self.fail_mode_status, {"error": "mode query failure"}
            agent_id = path.split("/")[3]
            if agent_id in self.modes:
                return 200, self.modes[agent_id]
            if agent_id in self.agents:
                return 200, {"mode": None}
            return 404, {"error": "agent not found"}

        if method == "GET" and path.startswith("/v0/agents/"):
            if self.on_preflight_hook:
                self.on_preflight_hook()
            agent_id = path.split("/")[3]
            if agent_id in self.agents:
                return 200, {"agent": self.agents[agent_id], "profiles": [], "slashCommands": []}
            return 404, {"error": "agent not found"}

        if method == "POST" and "/send" in path:
            agent_id = path.split("/")[3]
            self.received_messages.append({"agent_id": agent_id, "body": body})
            return 202, {"message": {"id": body.get("id"), "status": "pending", "delivery": body.get("delivery"), "runId": self.run_ids.get(agent_id)}}

        if method == "POST" and "/abort" in path:
            agent_id = path.split("/")[3]
            self.abort_bodies.append(body)
            expected = (body or {}).get("expectedRunId")
            if expected and self.active_run.get(agent_id, expected) != expected:
                return 409, {"error": "different active run"}
            self.aborted_agents.append(agent_id)
            return 202, {"agent": {"id": agent_id, "status": "idle"}}

        return 200, {}

# ---------------------------------------------------------------------------
# Happy API Adapter
# ---------------------------------------------------------------------------

class HappyAdapter:
    """High-level client for Happy Agent Base API with preflight and send validation."""

    def __init__(self, transport: Transport):
        self.transport = transport

    def live_allowed(self) -> bool:
        """Live mutation is permitted only for transports that explicitly opt in (test fakes).
        The real UnixSocketTransport never does; no flag or argument can change that."""
        return getattr(self.transport, "allows_live_mutation", False) is True

    def _require_live(self) -> None:
        if not self.live_allowed():
            raise LiveMutationDisabledError(
                "Live Happy send/abort is disabled: live dispatch integration is deferred "
                "(unresolved send/cancel race). Use submit/preview/preflight/admit only."
            )

    def is_agent_idle(self, agent_id: str) -> bool:
        """Returns True if the target agent currently reports status == 'idle'."""
        try:
            status_code, resp = self.transport.request("GET", f"/v0/agents/{agent_id}", {})
            if status_code == 200:
                agent_data = resp.get("agent")
                if isinstance(agent_data, dict):
                    return agent_data.get("status") == "idle"
            return False
        except Exception:
            return False

    def preflight_check(
        self, agent_id: str, pinned_provider: str, pinned_model: str, pinned_effort: str
    ) -> Dict[str, Any]:
        """
        Validates agent existence, idle status (busy agents are never steered), readable mode
        schema, and that the pinned model is in the installed catalog.
        FAILS CLOSED on missing, unauthorized, or malformed metadata. The daemon re-checks the
        mode against its live catalog at send time (400 -> SendRejectedError).
        """
        # 1. Check agent state
        status_code, resp = self.transport.request("GET", f"/v0/agents/{agent_id}", {})
        if status_code in (401, 403):
            raise AuthenticationError(f"Authentication failure querying agent {agent_id} (HTTP {status_code})")
        if status_code == 404:
            raise PreflightError(f"Target agent {agent_id} does not exist (HTTP 404)")
        if status_code != 200:
            raise PreflightError(f"Failed to query agent {agent_id}: HTTP {status_code}")

        agent_data = resp.get("agent") if isinstance(resp, dict) else None
        if not isinstance(agent_data, dict):
            raise PreflightError(f"Invalid agent payload for {agent_id}: missing agent object")
        agent_status = agent_data.get("status")
        if agent_status != "idle":
            raise AgentBusyError(f"Target agent {agent_id} is currently busy (status: '{agent_status}')")

        # Mode: GET /mode is the LAST SUBMITTED mode (null before the first message), not a
        # lock. A different current mode is fine for an idle agent: send carries the new mode.
        status_code, mode_resp = self.transport.request("GET", f"/v0/agents/{agent_id}/mode", {})
        if status_code in (401, 403):
            raise AuthenticationError(f"Authentication failure querying mode for {agent_id} (HTTP {status_code})")
        if status_code != 200:
            raise PreflightError(f"Failed to query mode for agent {agent_id}: HTTP {status_code}")
        if not isinstance(mode_resp, dict) or "mode" not in mode_resp:
            raise PreflightError(f"Invalid mode payload for {agent_id}: 'mode' key missing")
        mode_obj = mode_resp["mode"]
        if mode_obj is not None:
            fields = [mode_obj.get(k) if isinstance(mode_obj, dict) else None for k in ("providerId", "modelId", "effort")]
            if not all(isinstance(f, str) and f for f in fields):
                raise PreflightError(f"Agent {agent_id} reports a malformed mode object")

        if (pinned_provider, pinned_model, pinned_effort) not in MODEL_CATALOG.values():
            raise PreflightError(
                f"Requested {pinned_provider}/{pinned_model}/{pinned_effort} is not in the installed model "
                "catalog (capability unsupported)"
            )
        current = None if mode_obj is None else tuple(fields)
        return {"current_mode": current, "mode_switch": current != (pinned_provider, pinned_model, pinned_effort)}

    def send_assignment(
        self, agent_id: str, send_id: str, handoff_text: str, provider: str, model: str, effort: str
    ) -> Dict[str, Any]:
        """Sends assignment message with stable send_id. Retries with same send_id are idempotent."""
        self._require_live()
        body = {
            "id": send_id,
            "text": handoff_text,
            "delivery": "queue",
            "mode": {
                "providerId": provider,
                "modelId": model,
                "effort": effort,
                "serviceTier": None,
                "permissionMode": "auto",
            },
        }
        status_code, resp = self.transport.request("POST", f"/v0/agents/{agent_id}/send", {}, body=body)
        if status_code in (401, 403):
            raise AuthenticationError(f"Authentication failure during send to {agent_id} (HTTP {status_code})")
        if status_code in (400, 404, 409):
            raise SendRejectedError(f"Send rejected by daemon for {agent_id}: HTTP {status_code}")
        if status_code not in (200, 201, 202):
            raise ConnectionError(f"Unexpected send response for {agent_id}: HTTP {status_code}")
        # 202 is the documented success; a receipt proves acceptance only, not completion.
        msg = resp.get("message") if isinstance(resp, dict) else None
        if not isinstance(msg, dict) or msg.get("id") != send_id:
            raise ConnectionError(f"Send receipt for {agent_id} did not echo message id {send_id}")
        return resp

    def abort_agent(self, agent_id: str, expected_run_id: Optional[str]) -> bool:
        """
        Guarded abort. expectedRunId is mandatory: a different active run gives 409, so a newer
        message cannot be killed by mistake. Returns True only for 202 (acknowledged, NOT stopped).
        """
        self._require_live()
        if not expected_run_id:
            raise ValueError("Refusing unguarded abort: no authoritative run ID")
        status_code, _ = self.transport.request(
            "POST", f"/v0/agents/{agent_id}/abort", {}, body={"expectedRunId": expected_run_id}
        )
        return status_code in (200, 202)

# ---------------------------------------------------------------------------
# Coordinator Engine
# ---------------------------------------------------------------------------

class DispatchCoordinator:
    """The central deep module coordinating admission, preflight, dispatch, and reconciliation."""

    def __init__(self, ledger: JobLedger, adapter: HappyAdapter):
        self.ledger = ledger
        self.adapter = adapter

    def submit(
        self,
        job_id: str,
        owner: str,
        target: str,
        objective: str,
        inputs: str,
        provenance: Optional[str] = None,
        acceptance_checks: Optional[str] = None,
        eta_minutes: int = 15,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        risk: Optional[str] = None,
        kind: Optional[str] = None,
        claude_unavailable: Optional[str] = None,
        codex_unavailable: Optional[str] = None,
    ) -> Job:
        agent_id, spec = resolve_target_agent(target)
        job_kind = kind or (spec["kind"] if spec else "implementation")
        unavailable = claude_unavailable
        if not unavailable:
            blocked, err = self.ledger.is_provider_blocked("claude")
            if blocked:
                unavailable = f"persisted provider health: claude blocked ({err})"
        codex_down = codex_unavailable
        if not codex_down:
            blocked, err = self.ledger.is_provider_blocked("codex")
            if blocked:
                codex_down = f"persisted provider health: codex blocked ({err})"
        route = select_route(job_kind, risk, (provider, model, effort), unavailable, codex_down)

        payload = {
            "id": job_id,
            "owner": owner,
            "target_agent": agent_id,
            "kind": job_kind,
            "objective": objective,
            "inputs": inputs,
            "provenance": provenance,
            "acceptance_checks": acceptance_checks,
            "eta_minutes": eta_minutes,
            **route,
        }
        return self.ledger.submit_job(payload)

    def preflight(self, job_id: str) -> Tuple[bool, str]:
        job = self.ledger.get_job(job_id)
        try:
            self.adapter.preflight_check(job.target_agent, job.provider, job.model, job.effort)
            return True, f"Agent {job.target_agent} ready on {job.provider}/{job.model} ({job.effort})"
        except Exception as e:
            return False, sanitize_error_message(e)

    def preview_envelope(self, job_id: str) -> Dict[str, Any]:
        """
        Pure, non-mutating preview of the dispatch envelope and feasibility check.
        Does NOT alter job status or occupy a concurrency slot!
        """
        job = self.ledger.get_job(job_id)
        can_admit, admit_reason = self.ledger.can_admit(job_id)

        # Run preflight
        preflight_ok, preflight_msg = self.preflight(job_id)

        # Temporary send_id for preview
        preview_send_id = job.send_id or generate_send_id()
        temp_job = dataclasses.replace(job, send_id=preview_send_id)
        handoff_text = HandoffRenderer.render(temp_job)

        envelope = {
            "endpoint": f"/v0/agents/{job.target_agent}/send",
            "body": {
                "id": preview_send_id,
                "text": handoff_text,
                "delivery": "queue",
                "mode": {
                    "providerId": job.provider,
                    "modelId": job.model,
                    "effort": job.effort,
                    "serviceTier": None,
                    "permissionMode": "auto",
                },
            },
        }

        return {
            "ok": bool(can_admit and preflight_ok),
            "mode": "preview",
            "admission_feasible": can_admit,
            "admission_reason": admit_reason,
            "preflight_ok": preflight_ok,
            "preflight_message": preflight_msg,
            "job": job.to_dict(),
            "envelope": envelope,
            "notice": "Non-mutating preview generated. Ledger state was not altered.",
        }

    def dispatch(self, job_id: str, dry_run: bool = True) -> Dict[str, Any]:
        """
        Executes safe dispatch sequence:
        1. If dry_run=True, runs non-mutating preview_envelope().
        2. If live:
           a. Atomic admission check and transition to 'reserved'.
           b. Preflight verification. If failed, rolls back cleanly.
           c. Atomic compare-and-swap claim ('reserved' -> 'sending') before network send.
           d. POST /send with stable ID.
        """
        if dry_run:
            return self.preview_envelope(job_id)
        if not self.adapter.live_allowed():
            # Fail closed before any ledger mutation, reservation, or network call.
            raise LiveMutationDisabledError(
                "Live dispatch is disabled: integration deferred. No reservation made, nothing sent."
            )

        admitted_job = self.ledger.admit_job(job_id)
        if not admitted_job:
            current = self.ledger.get_job(job_id)
            return {
                "ok": False,
                "job": current.to_dict(),
                "reason": "Admission limit reached (max 2 global workers or target agent already busy)",
            }

        # Render handoff text
        handoff_text = HandoffRenderer.render(admitted_job)

        # Preflight verification
        try:
            self.adapter.preflight_check(
                admitted_job.target_agent,
                admitted_job.provider,
                admitted_job.model,
                admitted_job.effort,
            )
        except AuthenticationError as e:
            sanitized = sanitize_error_message(e)
            blocked_job = self.ledger.record_failure_and_maybe_block(
                job_id, cause="auth", error_msg=sanitized, definite_pre_send=True
            )
            return {"ok": False, "job": blocked_job.to_dict(), "reason": f"Auth preflight failure: {sanitized}"}
        except Exception as e:
            # Busy is a read-only observation (not a strike); every other preflight failure,
            # including transport errors, counts toward the two-strike limit.
            sanitized = sanitize_error_message(e)
            reverted_job = self.ledger.release_reservation_to_queued(
                job_id, reason=sanitized, is_capability_mismatch=not isinstance(e, AgentBusyError)
            )
            return {"ok": False, "job": reverted_job.to_dict(), "reason": f"Preflight rejected: {sanitized}"}

        # Atomic Compare-and-Swap Claim before transmitting any bytes!
        # If job was cancelled or attested stopped during preflight, claim_for_send returns False!
        claimed = self.ledger.claim_for_send(job_id)
        if not claimed:
            curr = self.ledger.get_job(job_id)
            return {
                "ok": False,
                "job": curr.to_dict(),
                "reason": f"Dispatch aborted: job status changed to '{curr.status}' during preflight. No network bytes sent.",
            }

        # Live execution outside SQLite transaction
        try:
            receipt = self.adapter.send_assignment(
                admitted_job.target_agent,
                admitted_job.send_id,
                handoff_text,
                admitted_job.provider,
                admitted_job.model,
                admitted_job.effort,
            )
            msg = (receipt or {}).get("message") or {}
            run_id = msg.get("runId") if isinstance(msg.get("runId"), str) else None
            running_job = self.ledger.mark_running(job_id, run_id=run_id)
            return {"ok": True, "mode": "live", "job": running_job.to_dict()}
        except AuthenticationError as e:
            sanitized = sanitize_error_message(e)
            blocked_job = self.ledger.record_failure_and_maybe_block(
                job_id, cause="auth", error_msg=sanitized, definite_pre_send=True
            )
            return {"ok": False, "job": blocked_job.to_dict(), "reason": f"Auth failure during send: {sanitized}"}
        except SendRejectedError as e:
            sanitized = sanitize_error_message(e)
            released = self.ledger.release_reservation_to_queued(job_id, reason=sanitized, is_capability_mismatch=True)
            return {"ok": False, "job": released.to_dict(), "reason": f"Send rejected (no message created): {sanitized}"}
        except Exception as e:
            sanitized = sanitize_error_message(e)
            ambiguous_job = self.ledger.record_ambiguous_send(job_id, error_msg=sanitized)
            return {
                "ok": False,
                "ambiguous": True,
                "job": ambiguous_job.to_dict(),
                "reason": (
                    f"Ambiguous send outcome ({sanitized}). Reservation retained. "
                    f"Check agent status and reconcile before retrying."
                ),
            }

    def cancel(self, job_id: str, stopped_attestation: Optional[str] = None, try_abort: bool = True) -> Job:
        job = self.ledger.get_job(job_id)
        if job.status in ("reserved", "sending", "running") and try_abort and job.run_id and self.adapter.live_allowed():
            try:
                self.adapter.abort_agent(job.target_agent, job.run_id)
            except Exception:
                pass
        # Without a known run ID no abort is issued: the job goes to cancel_pending and
        # needs a manual stop plus --stopped-attestation.

        return self.ledger.cancel_job(
            job_id,
            stopped_attestation=stopped_attestation,
        )

    def complete(self, job_id: str, evidence: str, stopped_attestation: Optional[str] = None) -> Job:
        return self.ledger.complete_job(
            job_id,
            result_evidence=evidence,
            stopped_attestation=stopped_attestation,
        )

# ---------------------------------------------------------------------------
# CLI Implementation
# ---------------------------------------------------------------------------

def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dispatch",
        description="Chief of Staff Dispatch Layer (atomic admission, preflight, durable ledger).",
    )
    parser.add_argument(
        "--db",
        type=pathlib.Path,
        default=pathlib.Path(".context/dispatch.db"),
        help="Path to SQLite ledger database (default: .context/dispatch.db)",
    )
    parser.add_argument(
        "--socket",
        type=pathlib.Path,
        default=pathlib.Path(os.path.expanduser("~/.happy/agent/server.sock")),
        help="Path to Happy daemon Unix domain socket",
    )
    parser.add_argument(
        "--token",
        type=pathlib.Path,
        default=pathlib.Path(os.path.expanduser("~/.happy/agent/token")),
        help="Path to Happy daemon auth token",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # submit
    p_sub = subparsers.add_parser("submit", help="Submit a job to the ledger")
    p_sub.add_argument("--id", required=True, help="Stable job identifier")
    p_sub.add_argument("--owner", required=True, help="Owning coordinator/agent ID")
    p_sub.add_argument("--target", required=True, help="Target specialist name or agent ID")
    p_sub.add_argument("--objective", required=True, help="Clear scientific claim or objective")
    p_sub.add_argument("--inputs", required=True, help="Exact input files or assigned references")
    p_sub.add_argument("--provenance", help="Reproducibility assumptions, seeds, assay lineage")
    p_sub.add_argument("--acceptance", help="Verification instructions and completion checks")
    p_sub.add_argument("--eta", type=int, default=15, help="Time budget in minutes (default: 15)")
    p_sub.add_argument("--risk", choices=list(RISKS), help="Job criticality; omitted fails safe to 'critical'")
    p_sub.add_argument("--kind", choices=list(KINDS), help="Job kind (default: from specialist roster)")
    p_sub.add_argument("--claude-unavailable", metavar="REASON", help="Explicit reason Claude is unavailable; routes critical implementation to ChatGPT Luna")
    p_sub.add_argument("--codex-unavailable", metavar="REASON", help="Explicit reason Codex/Sol is unavailable; research/planning then falls to Argon low")
    p_sub.add_argument("--provider", help="Override pinned provider")
    p_sub.add_argument("--model", help="Override pinned model")
    p_sub.add_argument("--effort", help="Override pinned effort")

    # list
    p_list = subparsers.add_parser("list", help="List jobs in ledger")
    p_list.add_argument("--status", choices=["queued", "reserved", "sending", "running", "completed", "blocked", "cancelled", "cancel_pending"])

    # show
    p_show = subparsers.add_parser("show", help="Show full job details and handoff")
    p_show.add_argument("--id", required=True, help="Job ID")

    # preflight
    p_pref = subparsers.add_parser("preflight", help="Run readiness and capability preflight")
    p_pref.add_argument("--id", required=True, help="Job ID")

    # preview
    p_prev = subparsers.add_parser("preview", help="Non-mutating preview of dispatch envelope")
    p_prev.add_argument("--id", required=True, help="Job ID")

    # admit
    p_adm = subparsers.add_parser(
        "admit",
        help="Reserve a ledger slot (local bookkeeping only: NOT a worker launch, no Happy access)",
    )
    p_adm.add_argument("--id", required=True, help="Job ID")

    # dispatch
    p_disp = subparsers.add_parser("dispatch", help="Atomically admit and dispatch job")
    p_disp.add_argument("--id", required=True, help="Job ID")
    p_disp.add_argument("--live", action="store_true", help="Perform live network send (default is non-mutating preview)")

    # complete
    p_comp = subparsers.add_parser("complete", help="Complete a job with verified result and stopped evidence")
    p_comp.add_argument("--id", required=True, help="Job ID")
    p_comp.add_argument("--evidence", required=True, help="Verification report / result evidence")
    p_comp.add_argument("--stopped-attestation", help="Explicit human/operator stopped attestation")

    # cancel
    p_canc = subparsers.add_parser("cancel", help="Cancel a job")
    p_canc.add_argument("--id", required=True, help="Job ID")
    p_canc.add_argument("--stopped-attestation", help="Explicit human/operator stopped attestation")
    p_canc.add_argument("--no-abort", action="store_true", help="Skip runtime abort call")

    # reconcile
    p_rec = subparsers.add_parser("reconcile", help="Reconcile an ambiguous, blocked, or pending job")
    p_rec.add_argument("--id", required=True, help="Job ID")
    p_rec.add_argument(
        "--action",
        required=True,
        choices=["confirm_running", "confirm_stopped", "unblock"],
        help="Reconciliation action",
    )
    p_rec.add_argument("--evidence", required=True, help="Auditable justification / evidence")

    # unblock-provider
    p_ubp = subparsers.add_parser("unblock-provider", help="Restore health for a blocked provider")
    p_ubp.add_argument("--provider", required=True, help="Provider ID (e.g. antigravity, codex, claude)")

    return parser

def main() -> None:
    parser = build_cli()
    args = parser.parse_args()

    ledger = JobLedger(args.db)
    transport = UnixSocketTransport(args.socket, args.token)
    adapter = HappyAdapter(transport)
    coordinator = DispatchCoordinator(ledger, adapter)

    try:
        if args.command == "submit":
            job = coordinator.submit(
                job_id=args.id,
                owner=args.owner,
                target=args.target,
                objective=args.objective,
                inputs=args.inputs,
                provenance=args.provenance,
                acceptance_checks=args.acceptance,
                eta_minutes=args.eta,
                provider=args.provider,
                model=args.model,
                effort=args.effort,
                risk=args.risk,
                kind=args.kind,
                claude_unavailable=args.claude_unavailable,
                codex_unavailable=args.codex_unavailable,
            )
            print(json.dumps(job.to_dict(), indent=2))

        elif args.command == "admit":
            current = ledger.get_job(args.id)
            notice = "Ledger reservation only. No worker was launched and nothing was sent to Happy."
            if current.status in ("reserved", "sending", "running", "cancel_pending"):
                res = {"ok": True, "already_reserved": True, "job": current.to_dict(), "notice": notice}
            else:
                reason = ledger.can_admit(args.id)[1]
                job = ledger.admit_job(args.id)
                if job:
                    res = {"ok": True, "already_reserved": False, "job": job.to_dict(), "notice": notice}
                else:
                    res = {"ok": False, "job": ledger.get_job(args.id).to_dict(), "reason": reason}
            print(json.dumps(res, indent=2))

        elif args.command == "list":
            jobs = ledger.list_jobs(status=args.status)
            out = [j.to_dict() for j in jobs]
            print(json.dumps(out, indent=2))

        elif args.command == "show":
            job = ledger.get_job(args.id)
            events = ledger.get_events(args.id)
            handoff = HandoffRenderer.render(job)
            res = {
                "job": job.to_dict(),
                "events": events,
                "handoff_rendered": handoff,
            }
            print(json.dumps(res, indent=2))

        elif args.command == "preflight":
            ok, msg = coordinator.preflight(args.id)
            print(json.dumps({"ok": ok, "message": msg}, indent=2))
            if not ok:
                sys.exit(1)

        elif args.command == "preview":
            res = coordinator.preview_envelope(args.id)
            print(json.dumps(res, indent=2))
            if not res.get("ok"):
                sys.exit(1)

        elif args.command == "dispatch":
            res = coordinator.dispatch(args.id, dry_run=(not args.live))
            print(json.dumps(res, indent=2))
            if not res.get("ok"):
                sys.exit(1)

        elif args.command == "complete":
            job = coordinator.complete(
                args.id, evidence=args.evidence, stopped_attestation=args.stopped_attestation
            )
            print(json.dumps(job.to_dict(), indent=2))

        elif args.command == "cancel":
            job = coordinator.cancel(
                args.id,
                stopped_attestation=args.stopped_attestation,
                try_abort=(not args.no_abort),
            )
            print(json.dumps(job.to_dict(), indent=2))

        elif args.command == "reconcile":
            job = ledger.reconcile_job(args.id, action=args.action, evidence=args.evidence)
            print(json.dumps(job.to_dict(), indent=2))

        elif args.command == "unblock-provider":
            ledger.unblock_provider(args.provider)
            print(json.dumps({"ok": True, "provider": args.provider, "status": "active"}, indent=2))

    except Exception as e:
        sanitized = sanitize_error_message(e)
        print(json.dumps({"error": sanitized, "type": type(e).__name__}, indent=2), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

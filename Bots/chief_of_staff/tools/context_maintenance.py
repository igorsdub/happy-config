#!/usr/bin/env python3
"""
Persistent-bot context-maintenance guard (runner: Chief of Tokens, every 30 minutes).

Optional, deterministic, stdlib-only (Python 3.9). Each registered bot seals its own CURRENT.md
inside its own folder (no daemon access). The runner then, only when every gate passes, asks the
daemon to run its NATIVE explicit compaction
(POST /v0/agents/:id/compact). Nothing else is ever mutated: no send, abort, archive, reset,
mode change, or history deletion. The code-level request guard enforces this.

Design facts (from the installed API.md):
- Compaction is idle-only and the daemon owns that validation (409 otherwise). Our idle snapshot
  is unguarded and may race; that is a known limitation, the endpoint is the authority.
- 202 means the compaction message exists in status "running". It is NOT completion. Completion
  is observed later as a `compaction` block with status completed/failed in GET /messages.
- Cadence, not size: there is no token threshold (user decision, 2026-11-01). A bot is compacted
  only when it is idle with nothing running and its newest message is unchanged since the
  previous runner cycle, i.e. it has done nothing for at least one 30-minute cycle.
- The local seal proves only that the bot ran its save step and that CURRENT.md has not changed
  since. It does not bind CURRENT.md to a conversation head; the runner-side head comparison is
  a separate check.
- A bot skipped for SKIP_REPORT_AFTER consecutive counted cycles is flagged once for reporting.
"""

from __future__ import annotations

import argparse
import fcntl
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
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOTS_ROOT = ROOT.parent
CHIEF_AGENT_ID = "fhti51x1qapqy7grqm3xoref"
DEFAULT_CHECKPOINT = ROOT / "CURRENT.md"
DEFAULT_STATE_DIR = ROOT / ".context"
REGISTRY_PATH = ROOT / "tools" / "bots.json"
SEAL_NAME = "checkpoint-seal.json"

REQUIRED_SECTIONS = (
    "Goal", "Status", "Decisions", "Constraints", "Artifacts",
    "Verification", "Open issues", "Next action",
)
MAX_CHECKPOINT_BYTES = 16 * 1024
COOLDOWN_SECONDS = 30 * 60
SKIP_REPORT_AFTER = 3
_ID_RE = re.compile(r"^[a-z][a-z0-9]{1,95}$")
ACTIVE_LEDGER_STATUSES = ("reserved", "sending", "running", "cancel_pending")
_PLACEHOLDERS = {"tbd", "todo", "...", "-", "n/a", "tbc", "<fill in>"}


def sanitize(msg: Any) -> str:
    text = str(msg)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9_\-\.~+/=]+", "Bearer [REDACTED]", text)
    text = re.sub(
        r"(?i)(token|secret|api[_-]?key|key|password)([\"']?\s*[=:]\s*|\s+)[\"']?[^\s\"',}]+",
        r"\1=[REDACTED]", text)
    return text


# ---------------------------------------------------------------------------
# Transport (Unix socket HTTP via http.client; token held in memory only)
# ---------------------------------------------------------------------------

class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, timeout: float = 10.0, sock: Optional[socket.socket] = None):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path
        self._preconnected = sock

    def connect(self) -> None:
        if self._preconnected is not None:
            self.sock = self._preconnected
            return
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


class UnixSocketTransport:
    def __init__(self, socket_path: pathlib.Path, token_path: pathlib.Path, timeout: float = 10.0):
        self.socket_path, self.token_path, self.timeout = str(socket_path), token_path, timeout

    def _token(self) -> str:
        env = os.environ.get("HAPPY_TOKEN")
        return env.strip() if env else self.token_path.read_text("utf-8").strip()

    def request(self, method: str, path: str, body: Optional[dict] = None) -> Tuple[int, Any]:
        payload = None if body is None else json.dumps(body).encode()
        headers = {"Authorization": f"Bearer {self._token()}", "Host": "localhost"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        conn = UnixHTTPConnection(self.socket_path, self.timeout)
        try:
            conn.request(method, path, body=payload, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            return resp.status, (json.loads(raw.decode()) if raw else {})
        finally:
            conn.close()


class GuardedTransport:
    """Executable guarantee: only snapshot reads and POST /compact on allowlisted targets."""

    def __init__(self, inner: Any, allowed_targets: List[str]):
        self.inner, self.allowed = inner, set(allowed_targets)
        self.calls: List[Tuple[str, str]] = []

    def request(self, method: str, path: str, body: Optional[dict] = None) -> Tuple[int, Any]:
        base = path.split("?", 1)[0]
        parts = base.strip("/").split("/")
        ok = False
        if method == "GET" and base == "/v0/config":
            ok = True
        elif len(parts) == 4 and parts[:2] == ["v0", "agents"] and parts[2] in self.allowed:
            ok = (method == "GET" and parts[3] in ("bootstrap", "messages")) or \
                 (method == "POST" and parts[3] == "compact")
        if not ok:
            raise PermissionError(f"Blocked request outside the maintenance allowlist: {method} {base}")
        self.calls.append((method, base))
        return self.inner.request(method, path, body)


# ---------------------------------------------------------------------------
# Checkpoint validation and sealing
# ---------------------------------------------------------------------------

def parse_sections(text: str) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for line in text.splitlines():
        m = re.match(r"^#{1,6}\s*(.+?)\s*:?\s*$", line)
        if m:
            current = m.group(1).strip().lower()
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return sections


def checkpoint_problems(raw: bytes) -> List[str]:
    problems: List[str] = []
    if len(raw) > MAX_CHECKPOINT_BYTES:
        problems.append(f"checkpoint is {len(raw)} bytes; limit {MAX_CHECKPOINT_BYTES}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return problems + ["checkpoint is not valid UTF-8"]
    headings = [m.group(1).strip().lower() for m in re.finditer(r"(?m)^#{1,6}\s*(.+?)\s*:?\s*$", text)]
    sections = parse_sections(text)
    for name in REQUIRED_SECTIONS:
        key = name.lower()
        if key not in sections:
            problems.append(f"missing section: {name}")
        elif headings.count(key) > 1:
            problems.append(f"duplicate section: {name}")
        else:
            body = "\n".join(sections[key]).strip()
            if not body:
                problems.append(f"empty section: {name}")
            elif body.lower() in _PLACEHOLDERS:
                problems.append(f"placeholder section: {name}")
    return problems


def atomic_write(path: pathlib.Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def seal_path(checkpoint: pathlib.Path) -> pathlib.Path:
    """The seal lives beside the checkpoint, inside the bot's own folder."""
    return pathlib.Path(checkpoint).parent / ".context" / SEAL_NAME


def load_registry(path: pathlib.Path = REGISTRY_PATH) -> Dict[str, Dict[str, Any]]:
    """name -> {agent_id, checkpoint (absolute)}. Malformed entries fail loudly."""
    raw = json.loads(pathlib.Path(path).read_text("utf-8"))
    if not isinstance(raw, dict) or not raw:
        raise ValueError("bot registry is empty or not an object")
    out: Dict[str, Dict[str, Any]] = {}
    for name, entry in raw.items():
        aid, cp = (entry or {}).get("agent_id"), (entry or {}).get("checkpoint")
        if not (isinstance(aid, str) and _ID_RE.match(aid) and isinstance(cp, str) and cp.endswith("CURRENT.md")):
            raise ValueError(f"malformed registry entry: {name}")
        resolved = (BOTS_ROOT / cp).resolve()
        if BOTS_ROOT.resolve() not in resolved.parents:
            raise ValueError(f"registry checkpoint escapes the Bots folder: {name}")
        out[name] = {"agent_id": aid, "checkpoint": resolved}
    return out


# ---------------------------------------------------------------------------
# Maintainer
# ---------------------------------------------------------------------------

class Maintainer:
    def __init__(
        self,
        transport: Any,
        state_dir: pathlib.Path = DEFAULT_STATE_DIR,
        allowed_targets: Optional[List[str]] = None,
        allowed_paths: Optional[List[pathlib.Path]] = None,
        now: Callable[[], float] = time.time,
        cooldown: int = COOLDOWN_SECONDS,
        dispatch_db: Optional[pathlib.Path] = None,
    ):
        self.targets = list(allowed_targets or [CHIEF_AGENT_ID])
        self.paths = [pathlib.Path(p).resolve() for p in (allowed_paths or [DEFAULT_CHECKPOINT])]
        self.api = GuardedTransport(transport, self.targets)
        self.state_dir = pathlib.Path(state_dir)
        self.now, self.cooldown = now, cooldown
        self.dispatch_db = dispatch_db if dispatch_db is not None else (self.state_dir / "dispatch.db")
        self.dispatch_db_explicit = dispatch_db is not None

    # -- allowlists ---------------------------------------------------------
    def _check_target(self, target: str) -> None:
        if target not in self.targets:
            raise PermissionError(f"Target {target} is not on the maintenance allowlist")

    def _check_path(self, path: pathlib.Path) -> pathlib.Path:
        if pathlib.Path(path).is_symlink():
            raise PermissionError("Checkpoint path must not be a symlink")
        resolved = pathlib.Path(path).resolve()
        if resolved not in self.paths:
            raise PermissionError(f"Checkpoint path {resolved} is not on the allowlist")
        return resolved

    # -- API reads ----------------------------------------------------------
    def _get(self, path: str) -> Any:
        status, data = self.api.request("GET", path)
        if status != 200 or not isinstance(data, dict):
            raise RuntimeError(f"GET {path.split('?')[0]} returned HTTP {status}")
        return data

    def latest_head(self, target: str) -> Optional[Dict[str, Any]]:
        """Newest message's id/role/createdAt only; content is never read or stored."""
        data = self._get(f"/v0/agents/{target}/messages?limit=1&omitToolData=true")
        runs = data.get("runs")
        if not isinstance(runs, list):
            raise RuntimeError("messages payload has no runs list")
        for run in reversed(runs):
            msgs = run.get("messages") if isinstance(run, dict) else None
            if isinstance(msgs, list) and msgs:
                m = msgs[-1]
                return {"id": m.get("id"), "role": m.get("role"), "createdAt": m.get("createdAt"),
                        "runId": run.get("id")}
        return None

    def snapshot(self, target: str) -> Tuple[Dict[str, Any], List[str]]:
        """Fresh bootstrap read. Returns (measurements, blockers). Unknown fields block."""
        boot = self._get(f"/v0/agents/{target}/bootstrap")
        blockers: List[str] = []
        agent = boot.get("agent")
        if not isinstance(agent, dict) or agent.get("id") != target:
            return {}, ["agent object missing or id mismatch"]
        def count(v: Any) -> bool:
            return isinstance(v, int) and not isinstance(v, bool) and v >= 0

        if "archivedAt" not in agent:
            blockers.append("archivedAt missing")
        elif agent["archivedAt"] is not None:
            blockers.append("agent is archived")
        if agent.get("status") != "idle":
            blockers.append(f"agent status is {agent.get('status')!r}, not idle")
        if "pendingQuestionId" not in agent:
            blockers.append("pendingQuestionId missing (question state unknown)")
        elif agent["pendingQuestionId"] is not None:
            blockers.append("a question is pending")
        if "wait" not in agent:
            blockers.append("wait state unknown")
        elif agent["wait"] is not None:
            blockers.append("a scheduled wait is active")

        pending = boot.get("pending")
        if not isinstance(pending, list):
            blockers.append("pending queue unobservable")
        elif pending:
            blockers.append(f"{len(pending)} pending queued/steer message(s)")

        sub = agent.get("subagents")
        if not (isinstance(sub, dict) and count(sub.get("running")) and count(sub.get("total"))):
            blockers.append("subagent counts unobservable or malformed")
        elif sub["running"] > 0:
            blockers.append(f"{sub['running']} child agent(s) running")
        children = boot.get("subagents")
        if not isinstance(children, list):
            blockers.append("subagent list missing or malformed")
        else:
            for child in children:
                if not isinstance(child, dict) or "archivedAt" not in child or "status" not in child:
                    blockers.append("malformed child agent entry")
                    break
                if child["archivedAt"] is None and child["status"] != "idle":
                    blockers.append("an active child agent exists")
                    break

        proc = agent.get("processes")
        if not (isinstance(proc, dict) and count(proc.get("running"))):
            blockers.append("background process count unobservable or malformed")
        elif proc["running"] > 0:
            blockers.append(f"{proc['running']} background process(es) running")
        procs = boot.get("processes")
        if not isinstance(procs, list):
            blockers.append("process list missing or malformed")
        else:
            for pr in procs:
                if not isinstance(pr, dict) or pr.get("status") not in ("running", "exited"):
                    blockers.append("malformed process entry")
                    break
                if pr["status"] == "running":
                    blockers.append("a background process is running")
                    break

        ctx = boot.get("context")
        meas: Dict[str, Any] = {"status": agent.get("status"), "updated_at_ms": agent.get("updatedAt")}
        if not isinstance(ctx, dict):
            blockers.append("context unmeasured (null after compaction/reset or before first inference)")
        else:
            tokens = ctx.get("contextTokens")
            # No threshold, so an approximate count is acceptable; it is reported, not gated.
            if not (isinstance(tokens, int) and not isinstance(tokens, bool) and tokens > 0):
                blockers.append("contextTokens malformed")
            if not isinstance(ctx.get("modelId"), str):
                blockers.append("context modelId malformed")
            meas.update(tokens=tokens, window=ctx.get("contextWindow"),
                        provider=ctx.get("providerId"), model=ctx.get("modelId"))
        blockers.extend(self._ledger_blockers(target))
        return meas, blockers

    def _ledger_blockers(self, target: str) -> List[str]:
        if target != CHIEF_AGENT_ID and not self.dispatch_db_explicit:
            return []  # the dispatch ledger records Chief of Staff's delegated jobs only
        db = self.dispatch_db
        if not db.exists():
            return [f"dispatch ledger {db} unreadable"] if self.dispatch_db_explicit else []
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
            try:
                q = "SELECT COUNT(*) FROM jobs WHERE status IN (%s)" % ",".join("?" * len(ACTIVE_LEDGER_STATUSES))
                n = conn.execute(q, ACTIVE_LEDGER_STATUSES).fetchone()[0]
            finally:
                conn.close()
        except Exception as e:
            return [f"dispatch ledger unreadable: {sanitize(e)}"]
        return [f"{n} unreconciled delegated job(s) in dispatch ledger"] if n else []


    # -- state --------------------------------------------------------------
    def state_path(self, target: str) -> pathlib.Path:
        """One state file per target, guarded by that target's lock (no cross-bot overwrite)."""
        return self.state_dir / f"context-maintenance-state-{target}.json"

    def _load_state(self, target: str) -> Dict[str, Any]:
        path = self.state_path(target)
        if not path.exists():
            return {}
        return json.loads(path.read_text("utf-8"))

    def _save_state(self, state: Dict[str, Any]) -> None:
        for target, st in state.items():
            atomic_write(self.state_path(target), json.dumps({target: st}, indent=2, sort_keys=True))

    class _Lock:
        def __init__(self, path: pathlib.Path):
            path.parent.mkdir(parents=True, exist_ok=True)
            self.f = open(path, "a+")
        def __enter__(self) -> bool:
            try:
                fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except OSError:
                return False
        def __exit__(self, *a: Any) -> None:
            self.f.close()

    # -- seal ---------------------------------------------------------------
    def seal(self, target: str, checkpoint: pathlib.Path) -> Dict[str, Any]:
        """Run by the bot itself as its last save step. Never contacts the daemon."""
        self._check_target(target)
        path = self._check_path(checkpoint)
        raw = path.read_bytes()
        problems = checkpoint_problems(raw)
        if problems:
            return {"ok": False, "action": "seal_rejected", "problems": problems}
        record = {
            "schema": 2, "path": str(path), "target": target,
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "sealed_at": iso(self.now()),
        }
        atomic_write(seal_path(path), json.dumps(record, indent=2, sort_keys=True))
        return {"ok": True, "action": "sealed", "record": record}

    def _verify_seal(self, target: str, path: pathlib.Path) -> Tuple[Optional[Dict[str, Any]], List[str]]:
        try:
            rec = json.loads(seal_path(path).read_text("utf-8"))
        except Exception:
            return None, ["no readable sealed checkpoint record"]
        if not isinstance(rec, dict):
            return None, ["sealed checkpoint record malformed"]
        problems: List[str] = []
        if rec.get("target") != target or rec.get("path") != str(path):
            problems.append("sealed record is for a different target or path")
        try:
            raw = path.read_bytes()
        except OSError:
            return rec, problems + ["checkpoint file unreadable"]
        if checkpoint_problems(raw):
            problems.append("checkpoint no longer validates")
        if hashlib.sha256(raw).hexdigest() != rec.get("sha256"):
            problems.append("checkpoint changed since seal (digest mismatch)")
        return rec, problems

    # -- reconcile ----------------------------------------------------------
    def reconcile(self, target: str, st: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Single read of recent history. Returns (state, detail); mutates `st` only on terminal results."""
        pending = st.get("pending")
        known = pending.get("compaction_id")
        if not known:
            # No receipt with a message id: never adopt by time or trigger. Operator reconciles.
            return "unknown", {"note": "no known compaction id (lost 202); operator reconciliation required; never retried"}
        data = self._get(f"/v0/agents/{target}/messages?limit=20&omitToolData=true")
        candidates = []
        for run in data.get("runs") or []:
            for m in (run.get("messages") if isinstance(run, dict) else None) or []:
                if not isinstance(m, dict) or m.get("id") != known:
                    continue
                blocks = m.get("content")
                if m.get("role") != "service" or not isinstance(blocks, list) or len(blocks) != 1:
                    return "unknown", {"note": "known compaction id has an unexpected message shape"}
                blk = blocks[0]
                if not (isinstance(blk, dict) and blk.get("type") == "compaction" and blk.get("trigger") == "manual"
                        and blk.get("status") in ("running", "completed", "failed")):
                    return "unknown", {"note": "known compaction id has an invalid compaction block"}
                candidates.append((known, blk))
        if len(candidates) != 1:
            return "unknown", {"note": f"{len(candidates)} matches for known compaction id; never retried blindly"}
        cid, block = candidates[0]
        status = block.get("status")
        if status == "running":
            pending["compaction_id"], pending["phase"] = cid, "accepted"
            return "running", {"compaction_id": cid}
        if status in ("completed", "failed"):
            st["last"] = {
                "outcome": status, "at": self.now(), "compaction_id": cid,
                "checkpoint_sha256": pending.get("checkpoint_sha256"), "head_id": pending.get("head_id"),
                "tokens_before": block.get("tokensBefore"), "tokens_after": block.get("tokensAfter"),
                "failure_reason": sanitize(block["failureReason"]) if block.get("failureReason") else None,
            }
            st["pending"] = None
            return status, {"compaction_id": cid}
        return "unknown", {"note": f"unrecognised compaction status {status!r}"}

    # -- maintain -----------------------------------------------------------
    def maintain(self, target: str, checkpoint: pathlib.Path) -> Dict[str, Any]:
        self._check_target(target)
        path = self._check_path(checkpoint)
        with self._Lock(self.state_dir / f"context-maintenance-{target}.lock") as got:
            if not got:
                return {"ok": True, "action": "skip", "reasons": ["another maintenance cycle holds the lock"]}
            return self._maintain_locked(target, path)

    def _maintain_locked(self, target: str, path: pathlib.Path) -> Dict[str, Any]:
        state = self._load_state(target)
        st = state.setdefault(target, {"pending": None, "last": None})
        try:
            out = self._cycle(target, path, state, st)
        except PermissionError:
            raise
        except Exception as e:
            out = {"ok": False, "action": "error_fail_closed", "reasons": [sanitize(e)]}
        return self._count_skip(state, st, out)

    def _count_skip(self, state: Dict[str, Any], st: Dict[str, Any], out: Dict[str, Any]) -> Dict[str, Any]:
        """Counted skips/errors in a row; flag once at SKIP_REPORT_AFTER. Quiet bots do not count."""
        action = out.get("action")
        if action in ("compact_requested", "compaction_completed") or out.get("quiet"):
            st["consecutive_skips"], st["reported"] = 0, False
        elif action in ("skip", "error_fail_closed"):
            st["consecutive_skips"] = int(st.get("consecutive_skips") or 0) + 1
            if st["consecutive_skips"] >= SKIP_REPORT_AFTER and not st.get("reported"):
                st["reported"] = True
                out["report"] = f"skipped {st['consecutive_skips']} cycles in a row"
        out["consecutive_skips"] = int(st.get("consecutive_skips") or 0)
        self._save_state(state)
        return out

    def _cycle(self, target: str, path: pathlib.Path, state: Dict[str, Any], st: Dict[str, Any]) -> Dict[str, Any]:
        if st.get("pending"):
            result, detail = self.reconcile(target, st)
            self._save_state(state)
            if st.get("pending"):
                return {"ok": result != "unknown", "action": f"pending_{result}", **detail,
                        "reasons": ["a maintenance attempt is not yet terminal; no new compaction"]}
            # Terminal: report it so the runner sees completion or failure; next cycle continues.
            last = st.get("last") or {}
            return {"ok": result == "completed", "action": f"compaction_{result}",
                    "compaction_id": last.get("compaction_id"), "tokens_before": last.get("tokens_before"),
                    "tokens_after": last.get("tokens_after"), "failure_reason": last.get("failure_reason")}

        # Runner-side freshness: the newest message must be unchanged since the previous cycle.
        head = self.latest_head(target)
        prev_id, st["seen_head"] = (st.get("seen_head") or {}).get("id"), head
        last = st.get("last") or {}
        if head and head.get("id") and head["id"] == last.get("compaction_id"):
            return {"ok": True, "action": "skip", "quiet": True,
                    "reasons": ["nothing new since the last compaction"]}
        if not head or not head.get("id"):
            return {"ok": True, "action": "skip", "quiet": True, "reasons": ["no conversation yet"]}
        if head["id"] != prev_id:
            return {"ok": True, "action": "skip", "quiet": prev_id is None,
                    "reasons": ["conversation changed since the previous cycle (or first sighting)"]}

        rec, problems = self._verify_seal(target, path)
        if problems:
            return {"ok": True, "action": "skip", "reasons": problems}
        meas, blockers = self.snapshot(target)
        if last.get("at") and self.now() - last["at"] < self.cooldown:
            blockers.append("cooldown after the previous attempt")
        if blockers:
            return {"ok": True, "action": "skip", "reasons": blockers, "measurement": meas}

        # Persist intent BEFORE the POST so a lost response is never retried blindly.
        why, info = "cadence", {"policy": "30-minute cadence, no token threshold"}
        st["pending"] = {
            "phase": "intent", "intent_id": secrets.token_hex(8), "compaction_id": None,
            "started_at": self.now(), "checkpoint_sha256": rec["sha256"],
            "head_id": head["id"], "tokens_before": meas.get("tokens"), "trigger": why,
        }
        self._save_state(state)
        return self._post_compact(target, state, st, meas, why, info)

    def _post_compact(self, target: str, state: Dict[str, Any], st: Dict[str, Any],
                      meas: Dict[str, Any], why: str, info: Dict[str, Any]) -> Dict[str, Any]:
        try:
            status, resp = self.api.request("POST", f"/v0/agents/{target}/compact", {})
        except PermissionError:
            raise
        except Exception as e:
            self._save_state(state)  # intent stays: outcome unknown
            return {"ok": False, "action": "pending_unknown",
                    "reasons": [f"compact outcome unknown ({sanitize(e)}); not retried"]}
        if status == 202:
            msg = resp.get("message") if isinstance(resp, dict) else None
            blocks = (msg or {}).get("content") or []
            block = blocks[0] if blocks and isinstance(blocks[0], dict) else {}
            if not (isinstance(msg, dict) and msg.get("id") and block.get("type") == "compaction"):
                self._save_state(state)
                return {"ok": False, "action": "pending_unknown", "reasons": ["202 without a compaction message"]}
            st["pending"].update(compaction_id=msg["id"], phase="accepted")
            self._save_state(state)
            return {"ok": True, "action": "compact_requested", "compaction_id": msg["id"],
                    "completed": False, "trigger": why, "measurement": meas, **info,
                    "note": "202 is acceptance only; completion is reconciled on a later cycle"}
        if status == 409:
            st["pending"] = None
            self._save_state(state)
            return {"ok": True, "action": "skip", "reasons": ["409: agent not idle or compaction already running"]}
        if status in (400, 401, 403, 404):
            st["pending"] = None
            st["last"] = {"outcome": "rejected", "at": self.now(), "http": status,
                          "checkpoint_sha256": None, "head_id": None}
            self._save_state(state)
            return {"ok": False, "action": "rejected", "reasons": [f"compact rejected: HTTP {status}"]}
        self._save_state(state)
        return {"ok": False, "action": "pending_unknown", "reasons": [f"compact returned HTTP {status}; not retried"]}

    def clear_pending(self, target: str, evidence: str) -> Dict[str, Any]:
        self._check_target(target)
        if not evidence.strip():
            raise ValueError("clear-pending requires auditable evidence")
        with self._Lock(self.state_dir / f"context-maintenance-{target}.lock") as got:
            if not got:
                return {"ok": False, "action": "locked"}
            state = self._load_state(target)
            st = state.setdefault(target, {"pending": None, "last": None})
            prior, st["pending"] = st.get("pending"), None
            st["last"] = {"outcome": "operator_cleared_unverified", "at": self.now(), "evidence": sanitize(evidence),
                          "checkpoint_sha256": None, "head_id": None}
            self._save_state(state)
            return {"ok": True, "action": "pending_cleared", "prior": prior}

    def inspect(self, target: str) -> Dict[str, Any]:
        self._check_target(target)
        meas, blockers = self.snapshot(target)
        state = self._load_state(target).get(target) or {}
        return {"ok": True, "action": "inspect", "measurement": meas, "blockers": blockers,
                "seen_head": state.get("seen_head"), "consecutive_skips": state.get("consecutive_skips", 0),
                "pending": state.get("pending"), "last": state.get("last")}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="context_maintenance", description=__doc__.split("\n\n")[0])
    home = os.environ.get("HAPPY_HOME_DIR") or os.path.expanduser("~/.happy")
    p.add_argument("--socket", type=pathlib.Path, default=pathlib.Path(home) / "agent" / "server.sock")
    p.add_argument("--token", type=pathlib.Path, default=pathlib.Path(home) / "agent" / "token")
    p.add_argument("--state-dir", type=pathlib.Path, default=DEFAULT_STATE_DIR)
    p.add_argument("--dispatch-db", type=pathlib.Path, help="Dispatch ledger to check (default .context/dispatch.db if present)")
    p.add_argument("--cooldown", type=int, default=COOLDOWN_SECONDS)
    sel = p.add_mutually_exclusive_group(required=True)
    sel.add_argument("--bot", action="append", help="Registry name; repeat for a pilot set")
    sel.add_argument("--all", action="store_true", help="Every registered bot")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("inspect", help="Read-only snapshot and gates")
    sub.add_parser("checkpoint-seal", help="Run by the bot itself: validate and digest its own CURRENT.md")
    sub.add_parser("maintain", help="One guarded cycle per bot: reconcile, gate, then POST /compact at most once")
    c = sub.add_parser("clear-pending", help="Operator override for an unknown pending attempt")
    c.add_argument("--evidence", required=True)
    return p


def main(argv: Optional[List[str]] = None, registry: pathlib.Path = REGISTRY_PATH) -> int:
    """`registry` is a test seam only; the CLI always uses the canonical tools/bots.json."""
    a = build_cli().parse_args(argv)
    try:
        reg = load_registry(registry)
        names = sorted(reg) if a.all else list(a.bot)
        unknown = [n for n in names if n not in reg]
        if unknown:
            raise PermissionError(f"not in the bot registry: {', '.join(unknown)}")
        if a.command == "checkpoint-seal" and len(names) != 1:
            raise ValueError("checkpoint-seal takes exactly one --bot (each bot seals its own)")
        if a.command == "checkpoint-seal":
            transport: Any = None  # sealing never contacts the daemon
        else:
            transport = UnixSocketTransport(a.socket, a.token)
        m = Maintainer(transport, a.state_dir, [reg[n]["agent_id"] for n in reg],
                       [reg[n]["checkpoint"] for n in reg], cooldown=a.cooldown, dispatch_db=a.dispatch_db)
        results: Dict[str, Any] = {}
        for n in names:
            aid, cp = reg[n]["agent_id"], reg[n]["checkpoint"]
            if a.command == "inspect":
                results[n] = m.inspect(aid)
            elif a.command == "checkpoint-seal":
                results[n] = m.seal(aid, cp)
            elif a.command == "maintain":
                results[n] = m.maintain(aid, cp)
            else:
                results[n] = m.clear_pending(aid, a.evidence)
    except Exception as e:
        print(json.dumps({"ok": False, "action": "error", "error": sanitize(e), "type": type(e).__name__}), file=sys.stderr)
        return 2
    print(json.dumps(results, indent=2, default=str))
    return 0 if all(r.get("ok") for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())

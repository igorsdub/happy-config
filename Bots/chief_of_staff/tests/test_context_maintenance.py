"""Tests for tools/context_maintenance.py against a stateful fake daemon (documented API shapes)."""

from __future__ import annotations

import copy
import json
import pathlib
import socket
import sqlite3
import tempfile
import threading
import unittest

from tools.context_maintenance import (
    CHIEF_AGENT_ID as CHIEF,
    SKIP_REPORT_AFTER,
    GuardedTransport,
    Maintainer,
    UnixHTTPConnection,
    load_registry,
    main,
    sanitize,
    seal_path,
)

GOOD = "\n".join(f"## {n}\nreal content for {n}\n" for n in (
    "Goal", "Status", "Decisions", "Constraints", "Artifacts", "Verification", "Open issues", "Next action"))
NOW = 2_000_000_000.0


class FakeDaemon:
    """Serves the documented bootstrap/messages/config/compact shapes and records every call."""

    def __init__(self):
        self.calls = []
        self.agent = {"id": CHIEF, "status": "idle", "archivedAt": None, "pendingQuestionId": None,
                      "wait": None, "subagents": {"total": 0, "running": 0}, "processes": {"running": 0},
                      "updatedAt": int((NOW - 60) * 1000)}
        self.boot = {"agent": self.agent, "pending": [], "processes": [], "subagents": [],
                     "context": {"approximate": False, "contextTokens": 90000, "contextWindow": 272000,
                                 "providerId": "claude", "modelId": "anthropic/opus-5-5"}}
        self.config = {"models": {"anthropic/opus-5-5": {"autoCompactWindow": 244800}}}
        self.messages = [{"id": "m1", "role": "user", "createdAt": 1},
                         {"id": "m2", "role": "agent", "createdAt": 2,
                          "content": [{"type": "tool_call", "name": "Bash"}]}]
        self.has_more = False
        self.compact_status, self.compact_body, self.compact_exc = 202, None, None
        self.service_blocks = {}

    def request(self, method, path, body=None):
        base = path.split("?")[0]
        self.calls.append((method, base))
        if method == "GET" and base == "/v0/config":
            return 200, self.config
        if method == "GET" and base.endswith("/bootstrap"):
            return 200, self.boot
        if method == "GET" and base.endswith("/messages"):
            msgs = list(self.messages) + [{"id": i, "role": "service", "createdAt": 3, "content": [b]}
                                          for i, b in self.service_blocks.items()]
            after = path.split("after=")[1].split("&")[0] if "after=" in path else None
            if after:
                ids = [m["id"] for m in msgs]
                msgs = msgs[ids.index(after) + 1:] if after in ids else msgs
            runs = []
            for m in msgs:
                rid = m.get("_run", "r1")
                if not runs or runs[-1]["id"] != rid:
                    runs.append({"id": rid, "messages": []})
                runs[-1]["messages"].append({k: v for k, v in m.items() if k != "_run"})
            return 200, {"runs": runs, "hasMore": self.has_more}
        if method == "POST" and base.endswith("/compact"):
            if self.compact_exc:
                raise self.compact_exc
            if self.compact_status == 202:
                blk = {"type": "compaction", "trigger": "manual", "status": "running", "tokensBefore": 90000,
                       "tokensAfter": None, "failureReason": None, "startedAt": int(NOW * 1000), "completedAt": None}
                self.service_blocks["c1"] = blk
                return 202, {"message": {"id": "c1", "role": "service", "content": [blk]}}
            return self.compact_status, {}
        raise AssertionError(f"unexpected call {method} {base}")

    def posts(self):
        return [c for c in self.calls if c[0] != "GET"]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.cp = self.dir / "CURRENT.md"
        self.cp.write_text(GOOD)
        self.d = FakeDaemon()
        self.clock = [NOW]
        self.make()

    def make(self, **kw):
        self.m = Maintainer(self.d, self.dir / "state", [CHIEF], [self.cp], now=lambda: self.clock[0],
                            dispatch_db=kw.pop("dispatch_db", None) or (self.dir / "none.db"), **kw)
        self.m.dispatch_db_explicit = False

    def tearDown(self):
        self.tmp.cleanup()

    def sealed(self):
        """Seal, then run the first-sighting cycle so the runner has seen the current head."""
        r = self.m.seal(CHIEF, self.cp)
        self.assertTrue(r["ok"], r)
        first = self.maintain()
        self.assertEqual((first["action"], first.get("quiet")), ("skip", True), first)
        return r

    def maintain(self):
        return self.m.maintain(CHIEF, self.cp)


class TestSeal(Base):
    def test_rejects_invalid_checkpoints(self):
        cases = {
            "missing": GOOD.replace("## Verification\nreal content for Verification\n", ""),
            "empty": GOOD.replace("real content for Goal", ""),
            "placeholder": GOOD.replace("real content for Status", "TBD"),
            "toolarge": GOOD + "x" * 17000,
            "duplicate": GOOD + "\n## Goal\nsecond\n",
        }
        for name, text in cases.items():
            self.cp.write_text(text)
            r = self.m.seal(CHIEF, self.cp)
            self.assertFalse(r["ok"], name)
            self.assertFalse(seal_path(self.cp).exists(), name)

    def test_seal_is_local_and_never_contacts_the_daemon(self):
        m = Maintainer(None, self.dir / "state", [CHIEF], [self.cp], now=lambda: NOW)
        rec = m.seal(CHIEF, self.cp)["record"]
        self.assertEqual(len(rec["sha256"]), 64)
        self.assertNotIn("summary", rec)
        self.assertNotIn("observed", rec)
        self.assertEqual(seal_path(self.cp), self.dir / ".context" / "checkpoint-seal.json")
        self.assertTrue(seal_path(self.cp).exists())
        self.assertEqual(self.d.calls, [])

    def test_path_and_target_allowlists(self):
        other = self.dir / "OTHER.md"
        other.write_text(GOOD)
        with self.assertRaises(PermissionError):
            self.m.seal(CHIEF, other)
        with self.assertRaises(PermissionError):
            self.m.seal("someoneelse", self.cp)
        link = self.dir / "link.md"
        link.symlink_to(self.cp)
        m2 = Maintainer(self.d, self.dir / "s2", [CHIEF], [link])
        with self.assertRaises(PermissionError):
            m2.seal(CHIEF, link)


class TestMaintainHappyPath(Base):
    def test_202_is_not_completion_and_lifecycle_reconciles(self):
        self.sealed()
        r = self.maintain()
        self.assertEqual((r["action"], r["completed"]), ("compact_requested", False))
        self.assertEqual(self.d.posts(), [("POST", f"/v0/agents/{CHIEF}/compact")])
        st = json.loads((self.dir / "state" / f"context-maintenance-state-{CHIEF}.json").read_text())[CHIEF]
        self.assertEqual(st["pending"]["compaction_id"], "c1")
        self.assertIsNone(st["last"])

        # next cycle: still running -> single read, no second POST
        r2 = self.maintain()
        self.assertEqual(r2["action"], "pending_running")
        self.assertEqual(len(self.d.posts()), 1)

        # terminal completed
        self.d.service_blocks["c1"].update(status="completed", tokensAfter=43000, completedAt=1)
        r3 = self.maintain()
        self.assertEqual((r3["action"], r3["ok"], r3["tokens_after"]), ("compaction_completed", True, 43000))
        st = json.loads((self.dir / "state" / f"context-maintenance-state-{CHIEF}.json").read_text())[CHIEF]
        self.assertIsNone(st["pending"])
        self.assertEqual((st["last"]["outcome"], st["last"]["tokens_after"]), ("completed", 43000))
        self.assertEqual(len(self.d.posts()), 1)

    def test_failed_compaction_is_recorded_and_cooldown_blocks_retry(self):
        self.sealed()
        self.maintain()
        self.d.service_blocks["c1"].update(status="failed", failureReason="provider Bearer abc123 broke")
        r = self.maintain()
        self.assertEqual((r["action"], r["ok"]), ("compaction_failed", False))
        self.assertNotIn("abc123", json.dumps(r))
        self.assertEqual(self.maintain()["action"], "skip")  # cooldown
        st = json.loads((self.dir / "state" / f"context-maintenance-state-{CHIEF}.json").read_text())[CHIEF]
        self.assertEqual(st["last"]["outcome"], "failed")
        self.assertNotIn("abc123", json.dumps(st))
        self.assertEqual(len(self.d.posts()), 1)

    def test_only_snapshot_reads_and_one_compact_post_no_reset_archive_abort_send_mode(self):
        self.sealed()
        self.maintain()
        self.maintain()
        for method, path in self.d.calls:
            self.assertTrue(method == "GET" or path.endswith("/compact"), (method, path))
        banned = ("abort", "archive", "send", "mode", "unarchive", "draft")
        self.assertFalse([c for c in self.d.calls if any(c[1].endswith("/" + b) for b in banned)])

    def test_guarded_transport_blocks_everything_else(self):
        g = GuardedTransport(self.d, [CHIEF])
        for method, path in (("POST", f"/v0/agents/{CHIEF}/abort"), ("POST", f"/v0/agents/{CHIEF}/archive"),
                             ("POST", f"/v0/agents/{CHIEF}/send"), ("GET", f"/v0/agents/{CHIEF}/mode"),
                             ("POST", "/v0/agents/other/compact"), ("DELETE", f"/v0/agents/{CHIEF}")):
            with self.assertRaises(PermissionError):
                g.request(method, path, {})
        self.assertEqual(self.d.calls, [])


class TestGates(Base):
    def blocked(self, why):
        self.sealed()
        r = self.maintain()
        self.assertEqual(r["action"], "skip", (why, r))
        self.assertEqual(self.d.posts(), [], why)
        return r

    def test_each_unsafe_state_blocks(self):
        mutations = {
            "busy": lambda d: d.agent.update(status="running_tools"),
            "question": lambda d: d.agent.update(pendingQuestionId="q1"),
            "wait": lambda d: d.agent.update(wait={"startedAt": 1, "dueAt": 2}),
            "archived": lambda d: d.agent.update(archivedAt=5),
            "pending": lambda d: d.boot.update(pending=[{"id": "x"}]),
            "pending_missing": lambda d: d.boot.pop("pending"),
            "question_missing": lambda d: d.agent.pop("pendingQuestionId"),
            "archived_missing": lambda d: d.agent.pop("archivedAt"),
            "neg_count": lambda d: d.agent.update(subagents={"total": 0, "running": -1}),
            "bool_count": lambda d: d.agent.update(processes={"running": False}),
            "lists_missing": lambda d: (d.boot.pop("subagents"), d.boot.pop("processes")),
            "malformed_child": lambda d: d.boot.update(subagents=["x"]),
            "child_status_missing": lambda d: d.boot.update(subagents=[{"archivedAt": None}]),
            "malformed_process": lambda d: d.boot.update(processes=[{"id": "p"}]),
            "child_running": lambda d: d.agent.update(subagents={"total": 1, "running": 1}),
            "child_count_missing": lambda d: d.agent.pop("subagents"),
            "child_listed_active": lambda d: d.boot.update(subagents=[{"status": "working", "archivedAt": None}]),
            "process": lambda d: d.agent.update(processes={"running": 1}),
            "process_missing": lambda d: d.agent.pop("processes"),
            "null_ctx": lambda d: d.boot.update(context=None),
            "malformed_tokens": lambda d: d.boot["context"].update(contextTokens="90000"),
            "bool_tokens": lambda d: d.boot["context"].update(contextTokens=True),
        }
        for name, mutate in mutations.items():
            self.setUp()
            self.sealed()
            mutate(self.d)
            r = self.maintain()
            self.assertEqual(r["action"], "skip", (name, r))
            self.assertEqual(self.d.posts(), [], name)
            self.tearDown()

    def test_no_token_threshold_small_and_approximate_contexts_compact(self):
        self.d.boot["context"].update(contextTokens=500, approximate=True)
        self.sealed()
        r = self.maintain()
        self.assertEqual((r["action"], r["trigger"]), ("compact_requested", "cadence"))

    def test_busy_bot_is_skipped_and_counted(self):
        self.sealed()
        self.d.agent.update(status="running_tools")
        r = self.maintain()
        self.assertEqual((r["action"], r["consecutive_skips"]), ("skip", 1))
        self.assertEqual(self.d.posts(), [])

    def test_dispatch_ledger_active_job_blocks(self):
        db = self.dir / "dispatch.db"
        c = sqlite3.connect(db)
        c.execute("CREATE TABLE jobs (id TEXT, status TEXT)")
        c.execute("INSERT INTO jobs VALUES ('j','running')")
        c.commit(); c.close()
        self.make(dispatch_db=db)
        r = self.blocked("ledger")
        self.assertTrue(any("delegated job" in x for x in r["reasons"]))
        c = sqlite3.connect(db); c.execute("UPDATE jobs SET status='cancelled'"); c.commit(); c.close()
        self.assertEqual(self.maintain()["action"], "compact_requested")

    def test_explicit_unreadable_ledger_fails_closed(self):
        self.m.dispatch_db_explicit = True
        self.m.dispatch_db = self.dir / "missing.db"
        r = self.blocked("ledger-missing")
        self.assertTrue(any("unreadable" in x for x in r["reasons"]))


class TestCheckpointIntegrity(Base):
    def test_changed_checkpoint_skips(self):
        self.sealed()
        self.cp.write_text(GOOD + "\nextra edit\n")
        r = self.maintain()
        self.assertEqual(r["action"], "skip")
        self.assertTrue(any("digest" in x for x in r["reasons"]))
        self.assertEqual(self.d.posts(), [])

    def test_checkpoint_made_invalid_after_seal_skips(self):
        self.sealed()
        self.cp.write_text("# Goal\nonly\n")
        self.assertEqual(self.maintain()["action"], "skip")

    def test_head_change_since_previous_cycle_skips_then_unchanged_compacts(self):
        self.sealed()
        self.d.messages.append({"id": "m3", "role": "user", "createdAt": 9})
        r = self.maintain()
        self.assertEqual(r["action"], "skip")
        self.assertTrue(any("changed since the previous cycle" in x for x in r["reasons"]))
        self.assertEqual(self.d.posts(), [])
        self.assertEqual(self.maintain()["action"], "compact_requested")

    def test_first_sighting_never_compacts(self):
        self.m.seal(CHIEF, self.cp)
        r = self.maintain()
        self.assertEqual((r["action"], r.get("quiet")), ("skip", True))
        self.assertEqual(self.d.posts(), [])

    def test_completed_compaction_is_not_repeated_without_new_activity(self):
        self.sealed()
        self.maintain()
        self.d.service_blocks["c1"].update(status="completed", tokensAfter=4000)
        self.assertEqual(self.maintain()["action"], "compaction_completed")
        for _ in range(4):
            self.clock[0] += 3600
            r = self.maintain()
            self.assertEqual((r["action"], r.get("quiet")), ("skip", True), r)
        self.assertEqual(len(self.d.posts()), 1)
        self.assertNotIn("report", r)

    def test_no_seal_skips(self):
        self.maintain()
        r = self.maintain()
        self.assertEqual(r["action"], "skip")
        self.assertTrue(any("sealed" in x for x in r["reasons"]))
        self.assertEqual(self.d.posts(), [])


class TestSkipReporting(Base):
    def test_report_once_after_consecutive_skips_and_reset_on_compaction(self):
        self.sealed()
        self.d.agent.update(status="running_tools")
        reports = []
        for _ in range(SKIP_REPORT_AFTER + 2):
            r = self.maintain()
            reports.append(r.get("report"))
        self.assertEqual(sum(1 for x in reports if x), 1)
        self.assertIsNotNone(reports[SKIP_REPORT_AFTER - 1])
        self.d.agent.update(status="idle")
        self.assertEqual(self.maintain()["action"], "compact_requested")
        st = json.loads((self.dir / "state" / f"context-maintenance-state-{CHIEF}.json").read_text())[CHIEF]
        self.assertEqual((st["consecutive_skips"], st["reported"]), (0, False))


class TestRegistryAndIsolation(Base):
    def write_reg(self, data):
        reg = self.dir / "bots.json"
        reg.write_text(json.dumps(data))
        return reg

    def test_registry_rejects_malformed_and_escaping_entries(self):
        good = {"a": {"agent_id": "abc123", "checkpoint": "a/CURRENT.md"}}
        self.assertEqual(load_registry(self.write_reg(good))["a"]["agent_id"], "abc123")
        for bad in ({}, {"a": {"agent_id": "Bad ID", "checkpoint": "a/CURRENT.md"}},
                    {"a": {"agent_id": "abc123", "checkpoint": "a/notes.md"}},
                    {"a": {"agent_id": "abc123", "checkpoint": "../../etc/CURRENT.md"}}):
            with self.assertRaises(ValueError, msg=bad):
                load_registry(self.write_reg(bad))

    def test_real_registry_lists_thirteen_bots(self):
        reg = load_registry()
        self.assertEqual(len(reg), 13)
        self.assertEqual(len({v["agent_id"] for v in reg.values()}), 13)

    def test_per_target_isolation(self):
        other_id, other_cp = "otherbot1", self.dir / "other" / "CURRENT.md"
        other_cp.parent.mkdir()
        other_cp.write_text(GOOD)
        self.m = Maintainer(self.d, self.dir / "state", [CHIEF, other_id], [self.cp, other_cp],
                            now=lambda: self.clock[0], dispatch_db=self.dir / "none.db")
        self.m.dispatch_db_explicit = False
        self.sealed()
        self.assertNotEqual(seal_path(self.cp), seal_path(other_cp))
        with self.assertRaises(PermissionError):
            self.m.maintain("notlisted", self.cp)
        self.assertEqual(self.maintain()["action"], "compact_requested")
        self.assertFalse((self.dir / "state" / f"context-maintenance-state-{other_id}.json").exists())

    def test_concurrent_cycles_for_different_bots_keep_both_states(self):
        other_id = "otherbot1"
        self.m = Maintainer(self.d, self.dir / "state", [CHIEF, other_id], [self.cp],
                            now=lambda: self.clock[0], dispatch_db=self.dir / "none.db")
        # Interleave: CHIEF loads its state, another bot's cycle saves, then CHIEF saves.
        chief_state = self.m._load_state(CHIEF)
        chief_state.setdefault(CHIEF, {})["marker"] = 1
        self.m._save_state({other_id: {"pending": {"compaction_id": "keep"}, "last": None}})
        self.m._save_state(chief_state)
        self.assertEqual(self.m._load_state(other_id)[other_id]["pending"]["compaction_id"], "keep")
        self.assertEqual(self.m._load_state(CHIEF)[CHIEF]["marker"], 1)

    def test_cli_seal_needs_exactly_one_registered_bot(self):
        reg = self.write_reg({"a": {"agent_id": "abc123", "checkpoint": "a/CURRENT.md"},
                              "b": {"agent_id": "abd123", "checkpoint": "b/CURRENT.md"}})
        self.assertEqual(main(["--all", "checkpoint-seal"], registry=reg), 2)
        self.assertEqual(main(["--bot", "zzz", "checkpoint-seal"], registry=reg), 2)
        from tools.context_maintenance import build_cli
        with self.assertRaises(SystemExit):
            build_cli().parse_args(["--registry", str(reg), "--all", "inspect"])
        with self.assertRaises(SystemExit):
            build_cli().parse_args(["maintain", "--all"])  # selectors go before the command
        self.assertEqual(build_cli().parse_args(["--bot", "a", "--bot", "b", "maintain"]).bot, ["a", "b"])


class TestOutcomes(Base):
    def test_409_skips_without_pending_state(self):
        self.d.compact_status = 409
        self.sealed()
        r = self.maintain()
        self.assertEqual(r["action"], "skip")
        st = json.loads((self.dir / "state" / f"context-maintenance-state-{CHIEF}.json").read_text())[CHIEF]
        self.assertIsNone(st["pending"])
        self.d.compact_status = 202
        self.assertEqual(self.maintain()["action"], "compact_requested")  # 409 is not a cooldown event

    def test_unknown_network_outcome_is_never_blindly_retried(self):
        self.d.compact_exc = ConnectionError("reset Authorization: Bearer topsecret999")
        self.sealed()
        r = self.maintain()
        self.assertEqual(r["action"], "pending_unknown")
        self.assertNotIn("topsecret999", json.dumps(r))
        self.d.compact_exc = None
        r2 = self.maintain()
        self.assertEqual(r2["action"], "pending_unknown")
        self.assertFalse(r2["ok"])
        self.assertEqual(len(self.d.posts()), 1)  # only the original attempt

    def test_lost_202_is_never_adopted_by_heuristic(self):
        self.d.compact_exc = ConnectionError("timeout")
        self.sealed()
        self.maintain()
        self.d.service_blocks["c9"] = {"type": "compaction", "trigger": "manual", "status": "completed",
                                       "startedAt": int(NOW * 1000) + 1000}
        for _ in range(2):
            r = self.maintain()
            self.assertEqual(r["action"], "pending_unknown")
        st = json.loads((self.dir / "state" / f"context-maintenance-state-{CHIEF}.json").read_text())[CHIEF]
        self.assertIsNotNone(st["pending"])
        self.assertIsNone(st["last"])
        self.assertEqual(len(self.d.posts()), 1)

    def test_unknown_plus_plausible_manual_compaction_stays_unknown_no_claim(self):
        self.d.compact_exc = ConnectionError("timeout")
        self.sealed()
        self.maintain()
        self.d.service_blocks["c7"] = {"type": "compaction", "trigger": "manual", "status": "completed",
                                       "startedAt": int(NOW * 1000) + 10}
        self.assertEqual(self.maintain()["action"], "pending_unknown")
        st = json.loads((self.dir / "state" / f"context-maintenance-state-{CHIEF}.json").read_text())[CHIEF]
        self.assertIsNone(st["last"])
        self.assertIsNotNone(st["pending"])

    def test_known_id_with_invalid_shape_stays_unknown(self):
        self.sealed()
        self.maintain()
        self.d.service_blocks["c1"]["trigger"] = "automatic"
        self.assertEqual(self.maintain()["action"], "pending_unknown")
        self.d.service_blocks["c1"].update(trigger="manual", status="weird")
        self.assertEqual(self.maintain()["action"], "pending_unknown")

    def test_cli_cannot_expand_allowlist(self):
        from tools.context_maintenance import build_cli
        with self.assertRaises(SystemExit):
            build_cli().parse_args(["--allow-target", "x", "inspect"])

    def test_clear_pending_requires_evidence_and_enables_cooldown_gated_retry(self):
        self.d.compact_exc = ConnectionError("x")
        self.sealed()
        self.maintain()
        with self.assertRaises(ValueError):
            self.m.clear_pending(CHIEF, "  ")
        self.assertTrue(self.m.clear_pending(CHIEF, "operator confirmed no compaction ran")["ok"])
        st = json.loads((self.dir / "state" / f"context-maintenance-state-{CHIEF}.json").read_text())[CHIEF]
        self.assertEqual(st["last"]["outcome"], "operator_cleared_unverified")
        self.d.compact_exc = None
        self.assertEqual(self.maintain()["action"], "skip")  # cooldown
        self.clock[0] += 3600
        self.d.agent["updatedAt"] = int(self.clock[0] * 1000)
        self.assertEqual(self.maintain()["action"], "compact_requested")

    def test_http_5xx_is_unknown_and_4xx_is_definite(self):
        self.d.compact_status = 500
        self.sealed()
        self.assertEqual(self.maintain()["action"], "pending_unknown")
        self.setUp()
        self.d.compact_status = 400
        self.sealed()
        self.assertEqual(self.maintain()["action"], "rejected")
        st = json.loads((self.dir / "state" / f"context-maintenance-state-{CHIEF}.json").read_text())[CHIEF]
        self.assertIsNone(st["pending"])

    def test_cycle_lock_prevents_concurrent_maintenance(self):
        self.sealed()
        lock = Maintainer._Lock(self.dir / "state" / f"context-maintenance-{CHIEF}.lock")
        with lock as got:
            self.assertTrue(got)
            r = self.maintain()
        self.assertEqual(r["action"], "skip")
        self.assertEqual(self.d.posts(), [])

    def test_malformed_202_is_unknown_not_success(self):
        self.d.request_orig = self.d.request
        real = self.d.request
        def bad(method, path, body=None):
            if method == "POST":
                self.d.calls.append((method, path.split("?")[0]))
                return 202, {"message": {}}
            return real(method, path, body)
        self.d.request = bad
        self.sealed()
        self.assertEqual(self.maintain()["action"], "pending_unknown")


class TestTransportAndRedaction(unittest.TestCase):
    def test_real_http_framing_over_socketpair(self):
        a, b = socket.socketpair()
        seen = {}
        def server():
            head = b""
            while not head.endswith(b"\r\n\r\n"):
                head += b.recv(1)
            n = int([l.split(b":")[1] for l in head.split(b"\r\n") if l.lower().startswith(b"content-length")][0])
            body = b""
            while len(body) < n:
                body += b.recv(n - len(body))
            seen.update(head=head, body=body)
            out = b'{"ok":true}'
            b.sendall(b"HTTP/1.1 202 Accepted\r\nContent-Length: %d\r\n\r\n" % len(out) + out)
        t = threading.Thread(target=server); t.start()
        conn = UnixHTTPConnection("unused", sock=a)
        conn.request("POST", f"/v0/agents/{CHIEF}/compact", body=b"{}", headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        self.assertEqual((resp.status, json.loads(resp.read())), (202, {"ok": True}))
        t.join(5)
        self.assertTrue(seen["head"].startswith(f"POST /v0/agents/{CHIEF}/compact HTTP/1.1\r\n".encode()))
        self.assertEqual(seen["body"], b"{}")

    def test_sanitize_removes_tokens(self):
        out = sanitize('{"token": "abc123", "authorization": "Bearer q1w2"} key=zzz9')
        for leaked in ("abc123", "q1w2", "zzz9"):
            self.assertNotIn(leaked, out)


if __name__ == "__main__":
    unittest.main()

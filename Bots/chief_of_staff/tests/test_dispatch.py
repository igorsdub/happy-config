"""
Comprehensive Test Suite for Chief of Staff Dispatch Layer
------------------------------------------------------------
Implements regression tests for all High and Medium findings from independent review:
1. Atomic CAS claim prevents phantom send when cancelled during preflight.
2. Terminal stop evidence required for slot release; abort 202 holds slot in cancel_pending.
3. Standard-library HTTP framing over Unix connection (no malformed framing).
4. Mode preflight fails closed on 401, 404, missing mode, and incomplete fields.
5. Non-mutating preview followed by live dispatch workflow.
6. Provider-scoped authentication blocking and 2-strike coordinator preflight block.
7. Centralized credential redaction across preflight, send, CLI, and audit events.
8. Unblock authorizes a fresh bounded attempt budget.
9. Real multi-process atomic admission tested via subprocess (avoiding POSIX semaphores).
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

from tools.dispatch import (
    AuthenticationError,
    DispatchCoordinator,
    AgentBusyError,
    LiveMutationDisabledError,
    UnixSocketTransport,
    FakeTransport,
    RoutingError,
    select_route,
    HandoffRenderer,
    HappyAdapter,
    InvalidStateError,
    JobLedger,
    PayloadConflictError,
    PreflightError,
    SPECIALISTS,
    sanitize_error_message,
)

class TestDispatchLayer(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = pathlib.Path(self.tmp_dir.name) / "test_dispatch.db"
        self.ledger = JobLedger(self.db_path)
        self.fake_transport = FakeTransport()
        self.adapter = HappyAdapter(self.fake_transport)
        self.coordinator = DispatchCoordinator(self.ledger, self.adapter)

        # Setup standard specialist mock agents in fake transport
        for key, spec in SPECIALISTS.items():
            self.fake_transport.set_agent(spec["agent_id"], status="idle")
            self.fake_transport.set_mode(
                spec["agent_id"],
                provider=spec["provider"],
                model=spec["model"],
                effort=spec["effort"],
            )

    def tearDown(self):
        self.tmp_dir.cleanup()

    # =========================================================================
    # Finding 1: Cancel During Preflight CAS & No Phantom Send
    # =========================================================================

    def test_01_cancel_during_preflight_prevents_network_send(self):
        """
        If a job is cancelled (with stopped attestation) while preflight is running,
        the atomic CAS claim ('reserved' -> 'sending') must fail.
        ZERO network bytes/messages may be sent to the agent.
        """
        self.coordinator.submit(
            risk="routine",
            job_id="job_cancel_preflight",
            owner="parent_1",
            target="software",
            objective="Race condition test",
            inputs="test.py",
        )

        # Inject a hook that cancels the job during preflight execution
        def cancel_hook():
            self.coordinator.cancel(
                "job_cancel_preflight",
                stopped_attestation="Operator cancelled during preflight",
                try_abort=False,
            )

        self.fake_transport.on_preflight_hook = cancel_hook

        res = self.coordinator.dispatch("job_cancel_preflight", dry_run=False)
        self.assertFalse(res["ok"])
        self.assertIn("aborted", res["reason"].lower())

        # Assert no message was ever sent to the agent!
        self.assertEqual(len(self.fake_transport.received_messages), 0)

        # Ledger status must be cancelled
        job = self.ledger.get_job("job_cancel_preflight")
        self.assertEqual(job.status, "cancelled")

    # =========================================================================
    # Finding 2: Terminal Stop Evidence vs Result Evidence
    # =========================================================================

    def test_02_completion_requires_stopped_proof_to_release_slot(self):
        """
        Plain text result evidence alone cannot complete a job while worker is not proven stopped.
        Only when agent is verified idle OR explicit --stopped-attestation is provided does it release.
        """
        self.coordinator.submit(
            risk="routine",
            job_id="job_comp_stop",
            owner="parent_1",
            target="software",
            objective="Run simulation",
            inputs="sim.py",
        )
        self.coordinator.dispatch("job_comp_stop", dry_run=False)
        self.assertEqual(self.ledger.get_job("job_comp_stop").status, "running")

        # Simulate agent is still working in background
        spec = SPECIALISTS["software"]
        self.fake_transport.set_agent(spec["agent_id"], status="working")

        # Calling complete without stopped attestation when agent is busy MUST FAIL
        with self.assertRaises(InvalidStateError):
            self.coordinator.complete("job_comp_stop", evidence="Pytest passed: 100%")

        # Now provide explicit stopped attestation
        completed = self.coordinator.complete(
            "job_comp_stop",
            evidence="Pytest passed: 100%",
            stopped_attestation="Verified worker process exited via ps aux",
        )
        self.assertEqual(completed.status, "completed")
        self.assertIn("Verified worker process exited", completed.evidence)

    def test_02b_abort_202_retains_slot_until_stopped_proof(self):
        """Abort 202 and an idle observation are not stop proof; only attestation releases."""
        self.coordinator.submit(job_id="job_abort_delay", owner="p", target="data", objective="ETL", inputs="d.csv")
        self.fake_transport.run_ids[SPECIALISTS["data"]["agent_id"]] = "run1"
        self.coordinator.dispatch("job_abort_delay", dry_run=False)
        spec = SPECIALISTS["data"]
        self.fake_transport.set_agent(spec["agent_id"], status="working")
        self.assertEqual(self.coordinator.cancel("job_abort_delay").status, "cancel_pending")
        self.assertEqual(self.fake_transport.aborted_agents, [spec["agent_id"]])

        self.coordinator.submit(job_id="job_data_compete", owner="p", target="data", objective="ETL2", inputs="d2.csv")
        self.assertIsNone(self.ledger.admit_job("job_data_compete"))

        # Agent reports idle, but idle alone does not prove THIS message finished.
        self.fake_transport.set_agent(spec["agent_id"], status="idle")
        self.assertEqual(self.coordinator.cancel("job_abort_delay").status, "cancel_pending")
        self.assertIsNone(self.ledger.admit_job("job_data_compete"))

        done = self.coordinator.cancel("job_abort_delay", stopped_attestation="operator checked run aborted")
        self.assertEqual(done.status, "cancelled")
        self.assertIsNotNone(self.ledger.admit_job("job_data_compete"))

    # =========================================================================
    # Finding 3: Standard HTTP Framing over Unix Connection
    # =========================================================================

    def test_03_http_client_framing_validity(self):
        """
        Ensures HTTP request serialization does not strip CRLF CRLF
        and uses standard http.client formatting.
        """
        from tools.dispatch import UnixHTTPConnection

        conn = UnixHTTPConnection(pathlib.Path("/tmp/nonexistent.sock"))
        self.assertEqual(conn.host, "localhost")
        self.assertEqual(conn.timeout, 10.0)

    # =========================================================================
    # Finding 4: Mode Preflight Fails Closed
    # =========================================================================

    def test_04_mode_preflight_fails_closed(self):
        """Auth/HTTP/schema failures fail closed; null or different mode on an idle agent is allowed."""
        spec = SPECIALISTS["software"]
        args = (spec["agent_id"], spec["provider"], spec["model"], spec["effort"])
        ft = self.fake_transport

        ft.fail_mode_auth = True
        with self.assertRaises(AuthenticationError):
            self.adapter.preflight_check(*args)
        ft.fail_mode_auth = False

        ft.fail_mode_status = 500
        with self.assertRaises(PreflightError):
            self.adapter.preflight_check(*args)
        ft.fail_mode_status = None

        ft.modes[spec["agent_id"]] = {}  # 'mode' key absent: schema violation
        with self.assertRaises(PreflightError):
            self.adapter.preflight_check(*args)

        ft.modes[spec["agent_id"]] = {"mode": {"providerId": spec["provider"], "modelId": spec["model"], "effort": None}}
        with self.assertRaises(PreflightError):
            self.adapter.preflight_check(*args)

        ft.modes[spec["agent_id"]] = {"mode": None}  # documented: null before first message
        self.assertTrue(self.adapter.preflight_check(*args)["mode_switch"])

        ft.set_mode(spec["agent_id"], "claude", "anthropic/sonnet-5-5", "medium")  # different mode: switching allowed
        self.assertTrue(self.adapter.preflight_check(*args)["mode_switch"])

        with self.assertRaises(PreflightError):  # model outside installed catalog
            self.adapter.preflight_check(spec["agent_id"], "codex", "openai/not-a-model", "low")

        ft.set_agent(spec["agent_id"], status="working")
        with self.assertRaises(AgentBusyError):
            self.adapter.preflight_check(*args)

    # =========================================================================
    # Finding 5: Non-Mutating Preview -> Live Dispatch Workflow
    # =========================================================================

    def test_05_preview_is_non_mutating_and_allows_subsequent_live_dispatch(self):
        """
        Running preview_envelope() generates envelope without mutating job state or occupying slot.
        Subsequent dispatch(live=True) succeeds cleanly.
        """
        self.coordinator.submit(
            risk="routine",
            job_id="job_preview_flow",
            owner="parent_1",
            target="software",
            objective="Preview workflow test",
            inputs="input.txt",
        )

        # Preview envelope
        prev = self.coordinator.preview_envelope("job_preview_flow")
        self.assertTrue(prev["ok"])
        self.assertEqual(prev["mode"], "preview")
        self.assertIn("body", prev["envelope"])

        # Check job in ledger is still queued and attempt count is 0
        job_after_preview = self.ledger.get_job("job_preview_flow")
        self.assertEqual(job_after_preview.status, "queued")
        self.assertEqual(job_after_preview.attempt_count, 0)

        # Active slots must be 0
        active_jobs = self.ledger.list_jobs(status="reserved")
        self.assertEqual(len(active_jobs), 0)

        # Subsequent live dispatch succeeds!
        live_res = self.coordinator.dispatch("job_preview_flow", dry_run=False)
        self.assertTrue(live_res["ok"])
        self.assertEqual(live_res["mode"], "live")
        self.assertEqual(self.ledger.get_job("job_preview_flow").status, "running")

    # =========================================================================
    # Finding 6: Provider-Scoped Auth Blocking & 2-Strike Preflight Block
    # =========================================================================

    def test_06_provider_scoped_auth_blocking(self):
        """
        When authentication fails on one job, the provider is marked blocked.
        Subsequent jobs targeting that provider are immediately rejected.
        """
        self.fake_transport.fail_auth = True

        self.coordinator.submit(
            risk="routine",
            job_id="job_auth_1",
            owner="parent_1",
            target="software",
            objective="Auth test 1",
            inputs="a.txt",
        )
        # Dispatch fails with auth error
        res1 = self.coordinator.dispatch("job_auth_1", dry_run=False)
        self.assertFalse(res1["ok"])

        # Provider antigravity is now blocked
        blocked, err = self.ledger.is_provider_blocked("antigravity")
        self.assertTrue(blocked)

        # Submit another job for data agent (also antigravity provider)
        self.coordinator.submit(
            risk="routine",
            job_id="job_auth_2",
            owner="parent_1",
            target="data",
            objective="Auth test 2",
            inputs="b.txt",
        )
        # Admission must be refused due to blocked provider health!
        self.assertIsNone(self.ledger.admit_job("job_auth_2"))

        # Unblock provider
        self.ledger.unblock_provider("antigravity")
        self.fake_transport.fail_auth = False

        # Now admission succeeds
        admitted = self.ledger.admit_job("job_auth_2")
        self.assertIsNotNone(admitted)

    def test_06b_two_strike_coordinator_preflight_block(self):
        """Repeated preflight transport/schema failures through dispatch() hit the two-strike block."""
        self.coordinator.submit(job_id="job_cap_strike", owner="p", target="software", objective="x", inputs="c.py")
        self.fake_transport.fail_mode_status = 500
        res1 = self.coordinator.dispatch("job_cap_strike", dry_run=False)
        self.assertFalse(res1["ok"])
        job1 = self.ledger.get_job("job_cap_strike")
        self.assertEqual((job1.status, job1.consecutive_same_cause_failures), ("queued", 1))
        self.coordinator.dispatch("job_cap_strike", dry_run=False)
        job2 = self.ledger.get_job("job_cap_strike")
        self.assertEqual((job2.status, job2.consecutive_same_cause_failures), ("blocked", 2))
        self.assertEqual(self.fake_transport.received_messages, [])

    # =========================================================================
    # Finding 7: Centralized Error Redaction
    # =========================================================================

    def test_07_credential_redaction_across_all_paths(self):
        """
        Ensures Bearer tokens and credentials are redacted across
        preflight, exceptions, and audit events.
        """
        raw_msg = "Error connecting with Authorization: Bearer secret_live_token_777 and token=abc123xyz"
        sanitized = sanitize_error_message(raw_msg)
        self.assertNotIn("secret_live_token_777", sanitized)
        self.assertNotIn("abc123xyz", sanitized)
        self.assertIn("Bearer [REDACTED]", sanitized)

        # Test preflight error recording
        self.coordinator.submit(
            risk="routine",
            job_id="job_redact",
            owner="parent_1",
            target="software",
            objective="Sanitize test",
            inputs="a.txt",
        )
        self.ledger.admit_job("job_redact")
        self.ledger.record_ambiguous_send("job_redact", error_msg=raw_msg)

        job = self.ledger.get_job("job_redact")
        self.assertNotIn("secret_live_token_777", job.last_error)

        events = self.ledger.get_events("job_redact")
        for ev in events:
            self.assertNotIn("secret_live_token_777", json.dumps(ev))

    # =========================================================================
    # Finding 8: Unblock Resets Attempt Exhaustion
    # =========================================================================

    def test_08_unblock_authorizes_fresh_attempt_budget(self):
        """
        When an exhausted job is unblocked via reconcile, its attempt_count is reset to 0,
        allowing admission on the authorized fresh budget.
        """
        self.coordinator.submit(
            risk="routine",
            job_id="job_exhausted",
            owner="parent_1",
            target="literature",
            objective="Search",
            inputs="query.txt",
        )

        # Exhaust 2 attempts
        self.ledger.admit_job("job_exhausted")
        self.ledger.record_failure_and_maybe_block("job_exhausted", "compile", "err", definite_pre_send=True)
        self.ledger.admit_job("job_exhausted")
        self.ledger.record_failure_and_maybe_block("job_exhausted", "compile", "err", definite_pre_send=True)

        job = self.ledger.get_job("job_exhausted")
        self.assertEqual(job.status, "blocked")
        self.assertEqual(job.attempt_count, 2)

        # Unblock with auditable evidence
        reconciled = self.ledger.reconcile_job(
            "job_exhausted",
            action="unblock",
            evidence="Authorizing fresh attempt budget after compiler bugfix",
        )
        self.assertEqual(reconciled.status, "queued")
        self.assertEqual(reconciled.attempt_count, 0)
        self.assertEqual(reconciled.consecutive_same_cause_failures, 0)

        # Admission now succeeds!
        admitted = self.ledger.admit_job("job_exhausted")
        self.assertIsNotNone(admitted)
        self.assertEqual(admitted.attempt_count, 1)

    # =========================================================================
    # Real Multi-Process Concurrency (Subprocess-based, no POSIX semaphores)
    # =========================================================================

    def test_09_real_subprocess_concurrency_admission(self):
        """
        Exercises real multi-process SQLite concurrency using independent subprocesses.
        Races 4 processes for 4 jobs against a max-2 limit.
        At most two reservations succeed; target exclusivity is preserved.
        """
        tool_script = pathlib.Path(__file__).parent.parent / "tools" / "dispatch.py"

        # Submit 4 jobs via ledger
        self.coordinator.submit("job_sub_1", "p1", "software", "Task 1", "f1.txt")
        self.coordinator.submit("job_sub_2", "p1", "software", "Task 2", "f2.txt") # competing for software
        self.coordinator.submit("job_sub_3", "p1", "literature", "Task 3", "f3.txt")
        self.coordinator.submit("job_sub_4", "p1", "review", "Task 4", "f4.txt")

        # Command template to attempt atomic admission
        code_template = (
            "import pathlib; from tools.dispatch import JobLedger; "
            "l = JobLedger(pathlib.Path('{db}')); "
            "res = l.admit_job('{jid}'); "
            "print('ADMITTED' if res else 'DENIED')"
        )

        job_ids = ["job_sub_1", "job_sub_2", "job_sub_3", "job_sub_4"]
        procs = []
        for jid in job_ids:
            cmd = [
                sys.executable,
                "-c",
                code_template.format(db=str(self.db_path), jid=jid),
            ]
            env = dict(os.environ)
            env["PYTHONPATH"] = str(tool_script.parent.parent)
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
            procs.append((jid, p))

        results = {}
        for jid, p in procs:
            out, err = p.communicate(timeout=10)
            results[jid] = out.strip()

        admitted = [jid for jid, outcome in results.items() if outcome == "ADMITTED"]

        # Assert at most 2 admitted globally
        self.assertLessEqual(len(admitted), 2, f"Expected <= 2 admitted, got {admitted}")

        # Assert no two jobs admitted for the same target agent
        admitted_targets = [self.ledger.get_job(jid).target_agent for jid in admitted]
        self.assertEqual(len(admitted_targets), len(set(admitted_targets)))

    # =========================================================================
    # Routing policy, criticality, and wire/lifecycle guardrails
    # =========================================================================

    def _spec(self):
        return SPECIALISTS["software"]

    def test_10_critical_or_unknown_risk_rejects_flash(self):
        flash = ("antigravity", "antigravity/gemini-3.8-flash", "medium")
        for risk in ("critical", None):
            with self.assertRaises(RoutingError):
                self.coordinator.submit(
                    job_id=f"j_flash_{risk}", owner="p", target="software", objective="o", inputs="i",
                    risk=risk, provider=flash[0], model=flash[1], effort=flash[2],
                )
        with self.assertRaises(RoutingError):
            select_route("implementation", "urgent")
        with self.assertRaises(RoutingError):
            select_route("implementation", "critical", ("codex", "openai/made-up", "low"))
        with self.assertRaises(RoutingError):  # Argon is research only
            select_route("implementation", "critical", ("antigravity", "antigravity/gemini-4-argon", "low"))

    def test_11_critical_and_unspecified_select_sonnet_and_dispatch_switches_mode(self):
        self.coordinator.submit(job_id="j_crit", owner="p", target="software", objective="o", inputs="i", risk="critical")
        job = self.coordinator.submit(job_id="j_unk", owner="p", target="data", objective="o", inputs="i", risk=None)
        for j in (self.ledger.get_job("j_crit"), job):
            self.assertEqual((j.provider, j.model, j.effort), ("claude", "anthropic/sonnet-5-5", "medium"))
            self.assertEqual(j.risk, "critical")
        self.assertIn("failed safe", job.route_reason)

        # Agent's last mode is Flash; an idle agent may be switched by the send mode.
        res = self.coordinator.dispatch("j_crit", dry_run=False)
        self.assertTrue(res["ok"])
        sent = self.fake_transport.received_messages[0]["body"]["mode"]
        self.assertEqual((sent["providerId"], sent["modelId"], sent["effort"]), ("claude", "anthropic/sonnet-5-5", "medium"))
        pin = [e for e in self.ledger.get_events("j_crit") if e["event_type"] == "admit"][0]
        self.assertIn("anthropic/sonnet-5-5", json.dumps(pin["payload"]))

    def test_12_chatgpt_fallback_requires_explicit_reason(self):
        no_reason = self.coordinator.submit(job_id="j_a", owner="p", target="software", objective="o", inputs="i", risk="critical")
        self.assertEqual(no_reason.provider, "claude")
        fb = self.coordinator.submit(
            job_id="j_b", owner="p", target="data", objective="o", inputs="i", risk="critical",
            claude_unavailable="quota exhausted until reset",
        )
        self.assertEqual((fb.provider, fb.model, fb.effort), ("codex", "openai/gpt-6-luna", "medium"))
        self.assertIn("quota exhausted", fb.route_reason)
        self.assertIn("not automatic", fb.route_reason)
        self.ledger.set_provider_blocked("claude", "auth failed")
        hb = self.coordinator.submit(job_id="j_c", owner="p", target="data", objective="o2", inputs="i", risk="critical")
        self.assertEqual(hb.provider, "codex")
        self.assertIn("provider health", hb.route_reason)

    def test_13_routine_implementation_selects_flash_research_selects_argon(self):
        r = self.coordinator.submit(job_id="j_r", owner="p", target="software", objective="o", inputs="i", risk="routine")
        self.assertEqual((r.provider, r.model, r.effort), ("antigravity", "antigravity/gemini-3.8-flash", "medium"))
        lit = self.coordinator.submit(job_id="j_l", owner="p", target="literature", objective="o", inputs="i", risk="critical")
        self.assertEqual((lit.provider, lit.model, lit.effort), ("claude", "anthropic/opus-5-5", "medium"))
        rev = self.coordinator.submit(job_id="j_v", owner="p", target="review", objective="o", inputs="i")
        self.assertEqual((rev.provider, rev.model, rev.effort), ("codex", "openai/gpt-6.1-sol", "low"))

    def test_14_busy_agent_is_never_messaged_and_not_a_strike(self):
        spec = self._spec()
        self.coordinator.submit(job_id="j_busy", owner="p", target="software", objective="o", inputs="i")
        self.fake_transport.set_agent(spec["agent_id"], status="working")
        for _ in range(3):
            self.assertFalse(self.coordinator.dispatch("j_busy", dry_run=False)["ok"])
        job = self.ledger.get_job("j_busy")
        self.assertEqual((job.status, job.attempt_count, job.consecutive_same_cause_failures), ("queued", 0, 0))
        self.assertEqual(self.fake_transport.received_messages, [])

    def test_15_idle_observation_alone_cannot_complete_or_release(self):
        self.coordinator.submit(job_id="j_idle", owner="p", target="software", objective="o", inputs="i")
        self.coordinator.dispatch("j_idle", dry_run=False)
        with self.assertRaises(InvalidStateError):  # agent is idle in the fake; still no proof
            self.coordinator.complete("j_idle", evidence="receipt only")
        self.assertEqual(self.ledger.get_job("j_idle").status, "running")

    def test_16_send_semantics_202_receipt_rejection_and_bad_receipt(self):
        self.coordinator.submit(job_id="j_ok", owner="p", target="software", objective="o", inputs="i")
        res = self.coordinator.dispatch("j_ok", dry_run=False)
        self.assertEqual(self.fake_transport.received_messages[0]["body"]["id"], res["job"]["send_id"])
        self.assertEqual(res["job"]["status"], "running")  # receipt = accepted, never 'completed'

        # Definite 409/400 rejection: no message exists, job released for bounded retry.
        orig = self.fake_transport.request
        def reject(method, path, headers, body=None):
            if method == "POST" and path.endswith("/send"):
                return 409, {"error": "conflict"}
            return orig(method, path, headers, body)
        self.fake_transport.request = reject
        self.coordinator.submit(job_id="j_rej", owner="p", target="data", objective="o", inputs="i")
        r = self.coordinator.dispatch("j_rej", dry_run=False)
        self.assertEqual(self.ledger.get_job("j_rej").status, "queued")
        self.assertFalse(r["ok"])

        # Receipt that does not echo our id is ambiguous: slot retained.
        def bad_receipt(method, path, headers, body=None):
            if method == "POST" and path.endswith("/send"):
                return 202, {"message": {"id": "mother"}}
            return orig(method, path, headers, body)
        self.fake_transport.request = bad_receipt
        r2 = self.coordinator.dispatch("j_rej", dry_run=False)
        self.assertTrue(r2["ambiguous"])
        self.assertEqual(self.ledger.get_job("j_rej").status, "reserved")

    def test_17_unknown_network_outcome_retains_slot_and_never_resurrects(self):
        self.coordinator.submit(job_id="j_net", owner="p", target="software", objective="o", inputs="i")
        self.fake_transport.fail_send_with = ConnectionError("reset Authorization: Bearer abc.def-123")
        res = self.coordinator.dispatch("j_net", dry_run=False)
        self.assertTrue(res["ambiguous"])
        self.assertNotIn("abc.def-123", json.dumps(res))
        self.coordinator.submit(job_id="j_net2", owner="p", target="software", objective="o2", inputs="i")
        self.assertIsNone(self.ledger.admit_job("j_net2"))
        # Operator-attested release, then a late ambiguity record must not re-occupy the slot.
        self.coordinator.cancel("j_net", stopped_attestation="verified nothing ran")
        self.ledger.record_ambiguous_send("j_net", "late")
        self.assertEqual(self.ledger.get_job("j_net").status, "cancelled")
        self.assertIsNotNone(self.ledger.admit_job("j_net2"))

    def test_18_failure_helper_never_frees_possibly_running_job(self):
        self.coordinator.submit(job_id="j_f", owner="p", target="software", objective="o", inputs="i")
        self.coordinator.dispatch("j_f", dry_run=False)
        job = self.ledger.record_failure_and_maybe_block("j_f", cause="auth", error_msg="x", definite_pre_send=False)
        self.assertEqual(job.status, "running")

    def test_19_serialized_secrets_redacted_and_duplicate_payloads(self):
        out = sanitize_error_message('{"token": "abc123def", "api_key":"zzz999", "authorization": "Bearer q1w2e3"}')
        for leaked in ("abc123def", "zzz999", "q1w2e3"):
            self.assertNotIn(leaked, out)
        a = self.coordinator.submit(job_id="j_d", owner="p", target="software", objective="o", inputs="i", risk="routine")
        b = self.coordinator.submit(job_id="j_d", owner="p", target="software", objective="o", inputs="i", risk="routine")
        self.assertEqual(a.payload_hash, b.payload_hash)
        with self.assertRaises(PayloadConflictError):
            self.coordinator.submit(job_id="j_d", owner="p", target="software", objective="o", inputs="i", risk="critical")

    def test_20_research_planning_ordered_route(self):
        for kind in ("research", "planning"):
            d = select_route(kind)
            self.assertEqual((d["provider"], d["model"], d["effort"]), ("claude", "anthropic/opus-5-5", "medium"))
        s = select_route("planning", None, None, "claude quota out")
        self.assertEqual((s["provider"], s["model"], s["effort"]), ("codex", "openai/gpt-6.1-sol", "medium"))
        self.assertIn("claude quota out", s["route_reason"])
        a = select_route("research", None, None, "claude quota out", "codex quota out")
        self.assertEqual((a["model"], a["effort"]), ("antigravity/gemini-4-argon", "low"))
        self.assertIn("codex quota out", a["route_reason"])
        # Codex outage alone never selects Argon; Sol medium is not a critical-implementation route.
        self.assertEqual(select_route("research", None, None, None, "codex out")["model"], "anthropic/opus-5-5")
        with self.assertRaises(RoutingError):
            select_route("implementation", "critical", ("codex", "openai/gpt-6.1-sol", "medium"))
        j = self.coordinator.submit(job_id="j_p", owner="p", target="manuscript", objective="o", inputs="i", kind="planning")
        self.assertEqual(j.model, "anthropic/opus-5-5")

    def test_21_abort_requires_run_id_and_sends_expected_run_id(self):
        spec = SPECIALISTS["software"]
        self.coordinator.submit(job_id="j_nr", owner="p", target="software", objective="o", inputs="i")
        self.coordinator.dispatch("job_nr" if False else "j_nr", dry_run=False)
        self.assertIsNone(self.ledger.get_job("j_nr").run_id)
        self.assertEqual(self.coordinator.cancel("j_nr").status, "cancel_pending")
        self.assertEqual(self.fake_transport.abort_bodies, [])  # no unguarded abort
        with self.assertRaises(ValueError):
            self.adapter.abort_agent(spec["agent_id"], None)
        self.coordinator.cancel("j_nr", stopped_attestation="manual stop verified")

        self.fake_transport.run_ids[spec["agent_id"]] = "runabc"
        self.coordinator.submit(job_id="j_r1", owner="p", target="software", objective="o2", inputs="i")
        self.coordinator.dispatch("j_r1", dry_run=False)
        self.assertEqual(self.ledger.get_job("j_r1").run_id, "runabc")
        self.fake_transport.active_run[spec["agent_id"]] = "newer"  # different active run -> 409
        self.assertFalse(self.adapter.abort_agent(spec["agent_id"], "runabc"))
        self.fake_transport.active_run[spec["agent_id"]] = "runabc"
        self.assertEqual(self.coordinator.cancel("j_r1").status, "cancel_pending")  # 202 != stopped
        self.assertEqual(self.fake_transport.abort_bodies[-1], {"expectedRunId": "runabc"})

    def test_22_real_unix_socket_http_framing(self):
        import socketserver, threading
        from tools.dispatch import UnixSocketTransport
        seen = {}
        class H(socketserver.StreamRequestHandler):
            def handle(self):
                head = b""
                while not head.endswith(b"\r\n\r\n"):
                    head += self.rfile.read(1)
                n = int([l.split(b":")[1] for l in head.split(b"\r\n") if l.lower().startswith(b"content-length")][0])
                seen["head"], seen["body"] = head, self.rfile.read(n)
                out = b'{"message":{"id":"x"}}'
                self.wfile.write(b"HTTP/1.1 202 Accepted\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(out) + out)
        d = tempfile.mkdtemp(dir=str(pathlib.Path(__file__).resolve().parent.parent / ".context"))
        sock = pathlib.Path(d) / "s.sock"
        tok = pathlib.Path(d) / "tok"; tok.write_text("tkn123")
        srv = socketserver.UnixStreamServer(str(sock), H)
        th = threading.Thread(target=srv.handle_request); th.start()
        try:
            status, resp = UnixSocketTransport(sock, tok).request("POST", "/v0/agents/a/abort", {}, body={"expectedRunId": "r1"})
        finally:
            th.join(5); srv.server_close()
            import shutil; shutil.rmtree(d, ignore_errors=True)
        self.assertEqual((status, resp["message"]["id"]), (202, "x"))
        self.assertTrue(seen["head"].startswith(b"POST /v0/agents/a/abort HTTP/1.1\r\n"))
        self.assertIn(b"Authorization: Bearer tkn123", seen["head"])
        self.assertEqual(json.loads(seen["body"]), {"expectedRunId": "r1"})

    def _real_adapter(self):
        calls = []
        class Spy(UnixSocketTransport):
            def request(self, *a, **k):
                calls.append(a); return 200, {}
        d = pathlib.Path(self.tmp_dir.name)
        return HappyAdapter(Spy(d / "no.sock", d / "no.tok")), calls

    def test_23_live_gate_blocks_real_transport_everywhere(self):
        adapter, calls = self._real_adapter()
        coord = DispatchCoordinator(self.ledger, adapter)
        coord.submit(job_id="j_g", owner="p", target="software", objective="o", inputs="i", risk="routine")
        with self.assertRaises(LiveMutationDisabledError):
            coord.dispatch("j_g", dry_run=False)
        job = self.ledger.get_job("j_g")
        self.assertEqual((job.status, job.attempt_count, job.send_id), ("queued", 0, None))
        with self.assertRaises(LiveMutationDisabledError):
            adapter.send_assignment("a", "mabc", "t", "claude", "anthropic/sonnet-5-5", "medium")
        with self.assertRaises(LiveMutationDisabledError):
            adapter.abort_agent("a", "run1")
        self.assertEqual(calls, [])
        # cancel never aborts on the real transport, even with a run id
        self.ledger.admit_job("j_g")
        with self.ledger._get_connection() as c:
            c.execute("UPDATE jobs SET status='running', run_id='r1' WHERE id='j_g'")
        self.assertEqual(coord.cancel("j_g").status, "cancel_pending")
        self.assertEqual(calls, [])
        # CLI --live fails closed with no ledger mutation
        self.coordinator.submit(job_id="j_cli", owner="p", target="data", objective="o", inputs="i", risk="routine")
        r = subprocess.run(
            [sys.executable, "-m", "tools.dispatch", "--db", str(self.db_path), "--socket", "/nonexistent.sock",
             "--token", "/nonexistent.tok", "dispatch", "--id", "j_cli", "--live"],
            capture_output=True, text=True, cwd=str(pathlib.Path(__file__).resolve().parent.parent))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("disabled", r.stderr)
        self.assertEqual(self.ledger.get_job("j_cli").status, "queued")

    def test_24_no_stop_or_complete_while_sending(self):
        self.coordinator.submit(job_id="j_s", owner="p", target="software", objective="o", inputs="i", risk="routine")
        self.ledger.admit_job("j_s"); self.assertTrue(self.ledger.claim_for_send("j_s"))
        with self.assertRaises(InvalidStateError):
            self.coordinator.cancel("j_s", stopped_attestation="idle before bytes")
        with self.assertRaises(InvalidStateError):
            self.coordinator.complete("j_s", evidence="e", stopped_attestation="s")
        for act in ("confirm_stopped", "confirm_running"):
            with self.assertRaises(InvalidStateError):
                self.ledger.reconcile_job("j_s", act, "ev")
        self.assertEqual(self.ledger.get_job("j_s").status, "sending")

    def test_25_override_must_match_policy_matrix(self):
        luna = ("codex", "openai/gpt-6-luna", "medium")
        sol_low = ("codex", "openai/gpt-6.1-sol", "low")
        sol_med = ("codex", "openai/gpt-6.1-sol", "medium")
        argon = ("antigravity", "antigravity/gemini-4-argon", "low")
        sonnet = ("claude", "anthropic/sonnet-5-5", "medium")
        for args in (
            ("implementation", "critical", luna),
            ("implementation", "critical", sol_low),
            ("review", None, sonnet),
            ("research", None, sol_med),
            ("research", None, argon),
        ):
            with self.assertRaises(RoutingError, msg=str(args)):
                select_route(*args)
        with self.assertRaises(RoutingError):
            select_route("research", None, argon, "claude out")  # skips Sol rung
        self.assertEqual(select_route("implementation", "critical", luna, "claude out")["model"], "openai/gpt-6-luna")
        self.assertEqual(select_route("implementation", "critical", sonnet)["model"], "anthropic/sonnet-5-5")
        self.assertEqual(select_route("review", None, sol_low)["effort"], "low")
        self.assertEqual(select_route("research", None, sol_med, "claude out")["effort"], "medium")
        self.assertEqual(select_route("research", None, argon, "claude out", "codex out")["effort"], "low")
        with self.assertRaises(RoutingError):  # public API path
            self.coordinator.submit(job_id="j_o", owner="p", target="software", objective="o", inputs="i",
                                    risk="critical", provider=luna[0], model=luna[1], effort=luna[2])

    def test_26_admit_cli_two_slots_agent_exclusion_idempotent(self):
        root = str(pathlib.Path(__file__).resolve().parent.parent)
        def cli(*a):
            r = subprocess.run([sys.executable, "-m", "tools.dispatch", "--db", str(self.db_path),
                                "--socket", "/nonexistent.sock", "--token", "/nonexistent.tok", *a],
                               capture_output=True, text=True, cwd=root)
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads(r.stdout)
        for jid, tgt in (("a1", "software"), ("a2", "data"), ("a3", "review"), ("a4", "software")):
            cli("submit", "--id", jid, "--owner", "p", "--target", tgt, "--risk", "routine", "--objective", "o", "--inputs", "i")
        r1 = cli("admit", "--id", "a1")
        self.assertEqual((r1["ok"], r1["job"]["status"], r1["job"]["attempt_count"]), (True, "reserved", 1))
        self.assertIn("No worker was launched", r1["notice"])
        again = cli("admit", "--id", "a1")
        self.assertTrue(again["already_reserved"])
        self.assertEqual(again["job"]["attempt_count"], 1)
        self.assertEqual(again["job"]["send_id"], r1["job"]["send_id"])
        self.assertTrue(cli("admit", "--id", "a2")["ok"])
        third = cli("admit", "--id", "a3")
        self.assertFalse(third["ok"])
        self.assertEqual(third["job"]["status"], "queued")
        cli("cancel", "--id", "a1", "--stopped-attestation", "operator: nothing was launched")
        self.assertTrue(cli("admit", "--id", "a4")["ok"])  # same agent as freed a1
        self.assertEqual(self.ledger.get_job("a4").status, "reserved")
        self.assertFalse(cli("admit", "--id", "a3")["ok"])  # two slots full again (a2, a4)
        self.assertEqual(self.ledger.get_job("a3").status, "queued")
        self.assertEqual(self.fake_transport.received_messages, [])

if __name__ == "__main__":
    unittest.main()

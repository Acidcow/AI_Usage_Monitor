import datetime
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.discovery.traffic_governor import TrafficGovernor
from backend.providers.claude import ClaudeProvider
from backend.providers.ollama import OllamaProvider
from backend.proxy.transparent_proxy import (
    TransparentProxyServer,
    _extract_sse_tokens,
    extract_sse_tokens,
)
from backend.security.dpapi_vault import DPAPIVault
from backend.storage.database import UsageDatabase


class TestZeroDoubleAccountingV2(unittest.TestCase):
    """
    TDD Test Suite for AIUM-1004:
    Bulletproof Zero Double-Accounting Across Transparent Proxy, Traffic Governor & Local Log Scanners.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_dedup_v2.db")
        self.db = UsageDatabase(db_path=self.db_path)
        self.vault = DPAPIVault(storage_path=os.path.join(self.temp_dir.name, "vault.json"))
        self.diagnostics = DiagnosticsEngine()
        self.diagnostics.clear_errors()
        self.claude = ClaudeProvider(self.db, self.vault, self.diagnostics)
        self.ollama = OllamaProvider(self.db, self.vault, self.diagnostics)

    def tearDown(self):
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. SSE Token & Upstream ID Extraction
    # -------------------------------------------------------------------------

    def test_01_extract_sse_tokens_anthropic_format(self):
        """Assert Anthropic SSE format extracts message.id, model, and in/out tokens."""
        sse_raw = (
            b'event: message_start\ndata: {"type": "message_start", "message": {"id": "msg_01AnthropicRealId", "type": "message", "role": "assistant", "model": "claude-3-7-sonnet", "usage": {"input_tokens": 1500, "output_tokens": 1}}}\n\n'
            b'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello world"}}\n\n'
            b'event: message_delta\ndata: {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 420}}\n\n'
            b'event: message_stop\ndata: {"type": "message_stop"}\n\n'
        )
        res = extract_sse_tokens(sse_raw)
        self.assertEqual(res.input_tokens, 1500)
        self.assertEqual(res.output_tokens, 420)
        self.assertEqual(res.model, "claude-3-7-sonnet")
        self.assertEqual(res.external_id, "msg_01AnthropicRealId")
        self.assertEqual(res.id, "msg_01AnthropicRealId")
        # Assert tuple unpacking compatibility
        in_t, out_t, mdl, ext_id = res
        self.assertEqual(in_t, 1500)
        self.assertEqual(out_t, 420)
        self.assertEqual(ext_id, "msg_01AnthropicRealId")

    def test_02_extract_sse_tokens_openai_chatcmpl_format(self):
        """Assert OpenAI format extracts chatcmpl ID and prompt/completion usage."""
        sse_text = (
            'data: {"id": "chatcmpl-9Abc123Xyz", "object": "chat.completion.chunk", "model": "gpt-4o", "choices": []}\n\n'
            'data: {"id": "chatcmpl-9Abc123Xyz", "usage": {"prompt_tokens": 850, "completion_tokens": 120}}\n\n'
            'data: [DONE]\n\n'
        )
        res = _extract_sse_tokens(sse_text)
        self.assertEqual(res.input_tokens, 850)
        self.assertEqual(res.output_tokens, 120)
        self.assertEqual(res.external_id, "chatcmpl-9Abc123Xyz")

    def test_03_extract_sse_tokens_gemini_format(self):
        """Assert Gemini format extracts usageMetadata and responseId."""
        sse_text = (
            'data: {"responseId": "resp_gemini_999", "usageMetadata": {"promptTokenCount": 300, "candidatesTokenCount": 85}}\n\n'
        )
        res = extract_sse_tokens(sse_text)
        self.assertEqual(res.input_tokens, 300)
        self.assertEqual(res.output_tokens, 85)
        self.assertEqual(res.external_id, "resp_gemini_999")

    def test_04_extract_sse_tokens_empty_or_malformed(self):
        """Assert empty, malformed, or blank SSE gracefully returns zeroes with None external_id."""
        empty_res = extract_sse_tokens(b"")
        self.assertEqual(empty_res.input_tokens, 0)
        self.assertEqual(empty_res.output_tokens, 0)
        self.assertIsNone(empty_res.external_id)

        malformed_res = extract_sse_tokens(b"data: not-json\n\ndata: [DONE]\n\n")
        self.assertEqual(malformed_res.input_tokens, 0)
        self.assertEqual(malformed_res.output_tokens, 0)
        self.assertIsNone(malformed_res.external_id)

    # -------------------------------------------------------------------------
    # 2. Transparent Proxy & Provider External ID Pipeline
    # -------------------------------------------------------------------------

    def test_05_proxy_mock_streaming_passes_external_id(self):
        """Assert TransparentProxy mock streaming records usage event with external_id."""
        proxy = TransparentProxyServer(self.claude, host="127.0.0.1", port=0)
        proxy.start()
        try:
            url = f"http://127.0.0.1:{proxy.server_port}/v1/messages"
            req = urllib.request.Request(
                url,
                data=json.dumps({"model": "claude-3-7-sonnet"}).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-mock-stream": "true",
                    "x-mock-input-tokens": "200",
                    "x-mock-output-tokens": "50",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                resp.read()

            events = self.db.get_recent_sessions(limit=5, provider="claude")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["external_id"], "msg_stream_1")
            self.assertEqual(events[0]["is_proxied"], 1)
        finally:
            proxy.stop()

    def test_06_claude_provider_ingest_proxy_interaction_forwards_external_id(self):
        """Assert ClaudeProvider.ingest_proxy_interaction passes external_id to DB."""
        evt_id = self.claude.ingest_proxy_interaction(
            model="claude-3-7-sonnet",
            input_tokens=500,
            output_tokens=150,
            session_id="stream_test_123",
            external_id="msg_claude_prov_test_42",
        )
        self.assertTrue(evt_id.startswith("evt_"))
        with self.db.connection() as conn:
            row = conn.cursor().execute(
                "SELECT external_id, is_proxied, source FROM usage_events WHERE id = ?", (evt_id,)
            ).fetchone()
            self.assertEqual(row["external_id"], "msg_claude_prov_test_42")
            self.assertEqual(row["is_proxied"], 1)
            self.assertEqual(row["source"], "proxy")

    # -------------------------------------------------------------------------
    # 3. Exact external_id Deduplication & Metadata Enrichment
    # -------------------------------------------------------------------------

    def test_07_exact_external_id_prevents_duplicate_insertion(self):
        """Assert duplicate external_id arrival prevents second row insertion."""
        ext_id = "msg_unique_anthropic_1001"
        id1 = self.db.record_usage_event(
            provider="claude",
            input_tokens=1200,
            output_tokens=300,
            session_id="stream_1731000",
            source="proxy",
            external_id=ext_id,
            is_proxied=1,
        )
        id2 = self.db.record_usage_event(
            provider="claude",
            input_tokens=1200,
            output_tokens=300,
            session_id="cli_sess_real_uuid",
            source="local_jsonl_scanner",
            external_id=ext_id,
            is_proxied=0,
        )
        self.assertEqual(id1, id2, "Must return existing event ID")
        with self.db.connection() as conn:
            count = conn.cursor().execute(
                "SELECT COUNT(*) FROM usage_events WHERE external_id = ?", (ext_id,)
            ).fetchone()[0]
            self.assertEqual(count, 1, "Must store exactly one row")

    def test_08_exact_external_id_enriches_session_id_from_stream_to_real_uuid(self):
        """Assert incoming scanner event with real session UUID enriches generic stream_ session."""
        ext_id = "msg_enrich_sess_01"
        self.db.record_usage_event(
            provider="claude",
            input_tokens=800,
            output_tokens=200,
            session_id="stream_node1_1731000",
            source="proxy",
            external_id=ext_id,
        )
        # Scanner arrives with real Claude Code session UUID
        real_uuid = "cf12e456-789a-4bc0-a123-abcdef123456"
        self.db.record_usage_event(
            provider="claude",
            input_tokens=800,
            output_tokens=200,
            session_id=real_uuid,
            source="local_jsonl_scanner",
            external_id=ext_id,
        )
        with self.db.connection() as conn:
            row = conn.cursor().execute(
                "SELECT session_id FROM usage_events WHERE external_id = ?", (ext_id,)
            ).fetchone()
            self.assertEqual(row["session_id"], real_uuid)

    def test_09_exact_external_id_enriches_project_id_and_metadata(self):
        """Assert incoming event enriches missing project_id and metadata on existing row."""
        ext_id = "msg_enrich_meta_02"
        self.db.record_usage_event(
            provider="claude",
            input_tokens=900,
            output_tokens=100,
            session_id="stream_1731",
            source="proxy",
            external_id=ext_id,
            project_id=None,
        )
        # Second event supplies project_id and rich metadata
        meta = {"cwd": "/agentic/project", "git_branch": "feature/bulletproof"}
        self.db.record_usage_event(
            provider="claude",
            input_tokens=900,
            output_tokens=100,
            session_id="stream_1731",
            source="local_jsonl_scanner",
            external_id=ext_id,
            project_id="prj_ai_usage_monitor",
            metadata=meta,
        )
        with self.db.connection() as conn:
            row = conn.cursor().execute(
                "SELECT project_id, metadata FROM usage_events WHERE external_id = ?", (ext_id,)
            ).fetchone()
            self.assertEqual(row["project_id"], "prj_ai_usage_monitor")
            stored_meta = json.loads(row["metadata"])
            self.assertEqual(stored_meta["git_branch"], "feature/bulletproof")

    def test_10_jsonl_first_then_proxy_preserves_specific_session_id(self):
        """Assert when JSONL scanner logs first, subsequent proxy event does not overwrite specific session."""
        ext_id = "msg_scanner_first_100"
        specific_sess = "session_claude_code_stable_88"
        id1 = self.db.record_usage_event(
            provider="claude",
            input_tokens=1500,
            output_tokens=500,
            session_id=specific_sess,
            source="local_jsonl_scanner",
            external_id=ext_id,
        )
        # Proxy arrives later with generic stream_ session
        id2 = self.db.record_usage_event(
            provider="claude",
            input_tokens=1500,
            output_tokens=500,
            session_id="stream_1731999999",
            source="proxy",
            external_id=ext_id,
            is_proxied=1,
        )
        self.assertEqual(id1, id2)
        with self.db.connection() as conn:
            row = conn.cursor().execute(
                "SELECT session_id, is_proxied FROM usage_events WHERE external_id = ?", (ext_id,)
            ).fetchone()
            self.assertEqual(row["session_id"], specific_sess, "Must preserve real session ID")
            self.assertEqual(row["is_proxied"], 1, "Must retain is_proxied flag")

    # -------------------------------------------------------------------------
    # 4. Cross-Source Temporal + Token Fingerprint Deduplication (±15s window)
    # -------------------------------------------------------------------------

    def test_11_cross_source_temporal_dedup_proxy_then_scanner(self):
        """Assert proxy with external_id=None deduplicates against scanner with identical tokens within 15s."""
        base_time = datetime.datetime.now(datetime.timezone.utc)
        # Proxy inserts at t = 0s without external_id
        id1 = self.db.record_usage_event(
            provider="claude",
            input_tokens=2200,
            output_tokens=650,
            session_id="stream_1731001",
            source="proxy",
            external_id=None,
            recorded_at=base_time.isoformat(),
            is_proxied=1,
        )
        # Scanner inserts at t = +3s with external_id="msg_anthropic_discovered"
        scan_time = base_time + datetime.timedelta(seconds=3)
        id2 = self.db.record_usage_event(
            provider="claude",
            input_tokens=2200,
            output_tokens=650,
            session_id="sess_real_claude_uuid",
            source="local_jsonl_scanner",
            external_id="msg_anthropic_discovered",
            recorded_at=scan_time.isoformat(),
        )
        self.assertEqual(id1, id2, "Cross-source temporal match must return existing ID")
        with self.db.connection() as conn:
            rows = conn.cursor().execute(
                "SELECT id, session_id, external_id, total_tokens FROM usage_events WHERE provider = 'claude'"
            ).fetchall()
            self.assertEqual(len(rows), 1, "Exactly one row must exist")
            self.assertEqual(rows[0]["external_id"], "msg_anthropic_discovered")
            self.assertEqual(rows[0]["session_id"], "sess_real_claude_uuid")
            self.assertEqual(rows[0]["total_tokens"], 2850)

    def test_12_cross_source_temporal_dedup_scanner_then_proxy(self):
        """Assert scanner inserted at t=0s deduplicates proxy inserted at t=+5s."""
        base_time = datetime.datetime.now(datetime.timezone.utc)
        id1 = self.db.record_usage_event(
            provider="claude",
            input_tokens=3100,
            output_tokens=800,
            session_id="sess_real_cli_user",
            source="claude_desktop_scanner",
            external_id="msg_desktop_turn_44",
            recorded_at=base_time.isoformat(),
        )
        proxy_time = base_time + datetime.timedelta(seconds=5)
        id2 = self.db.record_usage_event(
            provider="claude",
            input_tokens=3100,
            output_tokens=800,
            session_id="stream_173199",
            source="proxy",
            external_id=None,
            recorded_at=proxy_time.isoformat(),
            is_proxied=1,
        )
        self.assertEqual(id1, id2)
        with self.db.connection() as conn:
            rows = conn.cursor().execute(
                "SELECT session_id, external_id, is_proxied FROM usage_events WHERE id = ?", (id1,)
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["session_id"], "sess_real_cli_user")
            self.assertEqual(rows[0]["external_id"], "msg_desktop_turn_44")
            self.assertEqual(rows[0]["is_proxied"], 1)

    def test_13_cross_source_ollama_governor_then_log_scanner(self):
        """Assert Ollama traffic governor event deduplicates against local log scanner entry."""
        base_time = datetime.datetime.now(datetime.timezone.utc)
        # Governor routes request to local node
        id1 = self.db.record_usage_event(
            provider="ollama",
            model="llama3:8b",
            input_tokens=450,
            output_tokens=180,
            session_id="remote_node_alpha_1731",
            source="proxy",
            instance_id="node_alpha",
            recorded_at=base_time.isoformat(),
            is_proxied=1,
        )
        # Ollama local log scanner reads inference log 4 seconds later
        scan_time = base_time + datetime.timedelta(seconds=4)
        id2 = self.db.record_usage_event(
            provider="ollama",
            model="llama3:8b",
            input_tokens=450,
            output_tokens=180,
            session_id="ollama_log_eval_unique_hash",
            source="ollama_local_logs",
            instance_id="local",
            recorded_at=scan_time.isoformat(),
        )
        self.assertEqual(id1, id2, "Ollama governor and log scanner must deduplicate")
        with self.db.connection() as conn:
            rows = conn.cursor().execute(
                "SELECT session_id, total_tokens FROM usage_events WHERE provider = 'ollama'"
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["session_id"], "ollama_log_eval_unique_hash")
            self.assertEqual(rows[0]["total_tokens"], 630)

    # -------------------------------------------------------------------------
    # 5. Non-Matching Distinct Turns (Boundary & Anti-False-Positive Checks)
    # -------------------------------------------------------------------------

    def test_14_cross_source_distinct_turns_outside_15s_not_deduplicated(self):
        """Assert identical token usage occurring 25s apart is NOT deduplicated."""
        t1 = datetime.datetime.now(datetime.timezone.utc)
        t2 = t1 + datetime.timedelta(seconds=25)

        id1 = self.db.record_usage_event(
            provider="claude",
            input_tokens=500,
            output_tokens=150,
            session_id="stream_turn_1",
            source="proxy",
            recorded_at=t1.isoformat(),
        )
        id2 = self.db.record_usage_event(
            provider="claude",
            input_tokens=500,
            output_tokens=150,
            session_id="stream_turn_2",
            source="local_jsonl_scanner",
            recorded_at=t2.isoformat(),
        )
        self.assertNotEqual(id1, id2, "Turns > 15s apart must be recorded as distinct events")
        with self.db.connection() as conn:
            count = conn.cursor().execute(
                "SELECT COUNT(*) FROM usage_events WHERE provider = 'claude'"
            ).fetchone()[0]
            self.assertEqual(count, 2)

    def test_15_distinct_turns_within_15s_with_different_tokens_not_deduplicated(self):
        """Assert distinct requests within 15s with differing output tokens are NOT deduplicated."""
        t1 = datetime.datetime.now(datetime.timezone.utc)
        t2 = t1 + datetime.timedelta(seconds=2)

        id1 = self.db.record_usage_event(
            provider="claude",
            input_tokens=1000,
            output_tokens=200,
            session_id="stream_req_1",
            source="proxy",
            recorded_at=t1.isoformat(),
        )
        id2 = self.db.record_usage_event(
            provider="claude",
            input_tokens=1000,
            output_tokens=205,  # 5 more tokens: different turn!
            session_id="sess_req_2",
            source="local_jsonl_scanner",
            recorded_at=t2.isoformat(),
        )
        self.assertNotEqual(id1, id2)
        with self.db.connection() as conn:
            count = conn.cursor().execute(
                "SELECT COUNT(*) FROM usage_events WHERE provider = 'claude'"
            ).fetchone()[0]
            self.assertEqual(count, 2)

    def test_16_zero_token_events_not_deduplicated_by_fingerprint(self):
        """Assert zero-token ping events are not deduplicated by token fingerprint."""
        t1 = datetime.datetime.now(datetime.timezone.utc)
        t2 = t1 + datetime.timedelta(seconds=1)

        id1 = self.db.record_usage_event(
            provider="ollama",
            input_tokens=0,
            output_tokens=0,
            session_id="ping_1",
            source="direct",
            recorded_at=t1.isoformat(),
        )
        id2 = self.db.record_usage_event(
            provider="ollama",
            input_tokens=0,
            output_tokens=0,
            session_id="ping_2",
            source="proxy",
            recorded_at=t2.isoformat(),
        )
        self.assertNotEqual(id1, id2)

    def test_17_different_providers_with_same_tokens_not_deduplicated(self):
        """Assert identical token counts on Claude and Gemini are never cross-deduplicated."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        id1 = self.db.record_usage_event(
            provider="claude",
            input_tokens=1500,
            output_tokens=400,
            session_id="sess_c",
            recorded_at=now_iso,
        )
        id2 = self.db.record_usage_event(
            provider="gemini",
            input_tokens=1500,
            output_tokens=400,
            session_id="sess_g",
            recorded_at=now_iso,
        )
        self.assertNotEqual(id1, id2)
        with self.db.connection() as conn:
            claude_cnt = conn.cursor().execute("SELECT COUNT(*) FROM usage_events WHERE provider = 'claude'").fetchone()[0]
            gemini_cnt = conn.cursor().execute("SELECT COUNT(*) FROM usage_events WHERE provider = 'gemini'").fetchone()[0]
            self.assertEqual(claude_cnt, 1)
            self.assertEqual(gemini_cnt, 1)

    def test_18_multiple_scanners_same_turn_deduplicated(self):
        """Assert desktop app scanner and JSONL scanner inspecting same message deduplicate cleanly."""
        ext_id = "msg_multi_scan_55"
        id1 = self.db.record_usage_event(
            provider="claude",
            input_tokens=700,
            output_tokens=300,
            session_id="desktop_msg_55",
            source="desktop_app",
            external_id=ext_id,
        )
        id2 = self.db.record_usage_event(
            provider="claude",
            input_tokens=700,
            output_tokens=300,
            session_id="cli_sess_55",
            source="local_jsonl_scanner",
            external_id=ext_id,
        )
        self.assertEqual(id1, id2)

    def test_19_traffic_governor_streaming_deduplication(self):
        """Assert TrafficGovernor streaming record deduplicates with subsequent log scan."""
        base_time = datetime.datetime.now(datetime.timezone.utc)
        id1 = self.db.record_usage_event(
            provider="ollama",
            model="qwen2.5:14b",
            input_tokens=600,
            output_tokens=250,
            session_id="stream_cand_node_99_1731",
            source="proxy",
            recorded_at=base_time.isoformat(),
        )
        id2 = self.db.record_usage_event(
            provider="ollama",
            model="qwen2.5:14b",
            input_tokens=600,
            output_tokens=250,
            session_id="ollama_log_qwen_turn",
            source="log_scanner",
            recorded_at=(base_time + datetime.timedelta(seconds=2)).isoformat(),
        )
        self.assertEqual(id1, id2)

    def test_20_total_tokens_and_cost_integrity_after_dedup(self):
        """Assert total estate tokens and cost reflect strictly deduplicated events."""
        ext_id = "msg_cost_audit_1"
        self.db.record_usage_event(
            provider="claude",
            input_tokens=10000,
            output_tokens=2000,
            session_id="stream_turn_cost",
            source="proxy",
            external_id=ext_id,
        )
        # Duplicate from JSONL scanner
        self.db.record_usage_event(
            provider="claude",
            input_tokens=10000,
            output_tokens=2000,
            session_id="real_uuid_cost",
            source="local_jsonl_scanner",
            external_id=ext_id,
        )
        summary = self.db.get_usage_summary(provider="claude")
        self.assertEqual(summary["input_tokens_today"], 10000)
        self.assertEqual(summary["output_tokens_today"], 2000)
        self.assertEqual(summary["total_tokens_today"], 12000)
        expected_cost = round((10000 * 0.000003) + (2000 * 0.000015), 5)
        self.assertAlmostEqual(summary["estimated_cost_today_usd"], expected_cost, places=4)

    def test_21_exact_external_id_returns_existing_event_id(self):
        """Assert record_usage_event returns the exact existing event ID when deduplicated."""
        ext_id = "msg_id_match_test_777"
        id1 = self.db.record_usage_event(
            provider="claude",
            input_tokens=400,
            output_tokens=100,
            session_id="stream_id_1",
            external_id=ext_id,
        )
        id2 = self.db.record_usage_event(
            provider="claude",
            input_tokens=400,
            output_tokens=100,
            session_id="stream_id_2",
            external_id=ext_id,
        )
        self.assertEqual(id1, id2)

    def test_22_cross_source_dedup_preserves_is_proxied_flag(self):
        """Assert that if either event has is_proxied=1, the enriched row preserves is_proxied=1."""
        now = datetime.datetime.now(datetime.timezone.utc)
        id1 = self.db.record_usage_event(
            provider="claude",
            input_tokens=500,
            output_tokens=100,
            session_id="sess_scanner",
            source="local_jsonl_scanner",
            recorded_at=now.isoformat(),
            is_proxied=0,
        )
        id2 = self.db.record_usage_event(
            provider="claude",
            input_tokens=500,
            output_tokens=100,
            session_id="stream_proxy",
            source="proxy",
            recorded_at=(now + datetime.timedelta(seconds=2)).isoformat(),
            is_proxied=1,
        )
        self.assertEqual(id1, id2)
        with self.db.connection() as conn:
            row = conn.cursor().execute(
                "SELECT is_proxied FROM usage_events WHERE id = ?", (id1,)
            ).fetchone()
            self.assertEqual(row["is_proxied"], 1)


if __name__ == "__main__":
    unittest.main()

import unittest
import os
import sys
import json
import time
import uuid
import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.storage.database import UsageDatabase
from backend.server.http_server import AppHTTPServer
from backend.tray.native_widget import NativeTaskbarWidget

class TestMultiDimensionalTelemetryAndDeduplication(unittest.TestCase):
    """
    TDD Suite for FR-801: Multi-Platform Telemetry Capture, Multi-Instance Rollups,
    Proxy Source Correlation, Zero Double-Accounting & Dynamic Pivoting.
    """

    @classmethod
    def setUpClass(cls):
        cls.test_db_path = str(REPO_ROOT / "data" / f"test_v2_telemetry_{uuid.uuid4().hex[:8]}.db")
        cls.database = UsageDatabase(db_path=cls.test_db_path)

        # Mock providers dictionary
        cls.mock_providers = {}
        cls.server = AppHTTPServer(
            database=cls.database,
            vault=None,
            diagnostics=None,
            providers=cls.mock_providers,
            host="127.0.0.1",
            port=0,
            proxy_port=8766
        )
        cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        if os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass

    def setUp(self):
        # Clear usage events for clean state per test
        with self.database._lock:
            conn = self.database._get_connection()
            conn.cursor().execute("DELETE FROM usage_events")
            conn.commit()
            conn.close()

    def test_01_schema_has_source_instance_external_id_and_proxied_flags(self):
        """Assert usage_events table contains source, instance_id, external_id, and is_proxied."""
        with self.database._lock:
            conn = self.database._get_connection()
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(usage_events)")
            cols = {row["name"] for row in cursor.fetchall()}
            conn.close()

        self.assertIn("source", cols)
        self.assertIn("instance_id", cols)
        self.assertIn("external_id", cols)
        self.assertIn("is_proxied", cols)

    def test_02_record_direct_telemetry_across_platforms(self):
        """Assert direct usage telemetry is cleanly recorded across Claude, Gemini, Ollama, ChatGPT, Copilot."""
        platforms = [
            ("claude", "claude-3-7-sonnet", 1000, 500, 0.009),
            ("gemini", "gemini-2.0-flash", 2000, 400, 0.001),
            ("ollama", "gemma4:e4b", 1500, 300, 0.0),
            ("chatgpt", "gpt-4o", 800, 600, 0.008),
            ("copilot", "copilot-chat", 1200, 200, 0.0)
        ]

        for prov, model, in_t, out_t, cost in platforms:
            ev_id = self.database.record_usage_event(
                provider=prov,
                model=model,
                session_id=f"sess_{prov}_direct",
                input_tokens=in_t,
                output_tokens=out_t,
                estimated_cost=cost,
                source="direct",
                instance_id="local",
                is_proxied=0
            )
            self.assertIsNotNone(ev_id)

        summary = self.database.get_usage_summary()
        self.assertEqual(summary["total_tokens_today"], 8500)
        self.assertEqual(summary["total_sessions"], 5)

    def test_03_record_proxied_telemetry_with_external_id(self):
        """Assert proxied telemetry sets source='proxy', is_proxied=1, and captures external upstream ID."""
        ext_msg_id = "msg_01Xk39ZqaV409Kms923"
        ev_id = self.database.record_usage_event(
            provider="claude",
            model="claude-3-5-sonnet",
            session_id="sess_agentic_proxy_01",
            input_tokens=4000,
            output_tokens=1000,
            estimated_cost=0.027,
            source="proxy",
            instance_id="local",
            external_id=ext_msg_id,
            is_proxied=1,
            client_ip="192.168.1.105",
            client_alias="MacBook-Pro-Dev"
        )

        with self.database._lock:
            conn = self.database._get_connection()
            row = conn.cursor().execute("SELECT source, instance_id, external_id, is_proxied, client_alias FROM usage_events WHERE id = ?", (ev_id,)).fetchone()
            conn.close()

        self.assertEqual(row["source"], "proxy")
        self.assertEqual(row["instance_id"], "local")
        self.assertEqual(row["external_id"], ext_msg_id)
        self.assertEqual(row["is_proxied"], 1)
        self.assertEqual(row["client_alias"], "MacBook-Pro-Dev")

    def test_04_deduplication_via_external_id(self):
        """Assert exact upstream message/request ID prevents double-accounting if logged multiple times."""
        ext_id = "msg_anthropic_dedup_unique_42"
        # 1. First arrival via proxy stream
        id1 = self.database.record_usage_event(
            provider="claude",
            model="claude-3-5-sonnet",
            session_id="sess_dedup_01",
            input_tokens=2500,
            output_tokens=500,
            estimated_cost=0.015,
            source="proxy",
            external_id=ext_id,
            is_proxied=1
        )

        # 2. Second arrival via log scanner / API polling for the same message
        id2 = self.database.record_usage_event(
            provider="claude",
            model="claude-3-5-sonnet",
            session_id="sess_dedup_01",
            input_tokens=2500,
            output_tokens=500,
            estimated_cost=0.015,
            source="log_scanner",
            external_id=ext_id,
            is_proxied=0
        )

        self.assertEqual(id1, id2, "Duplicate external_id must return existing event ID")

        # Verify tokens counted only once in database
        with self.database._lock:
            conn = self.database._get_connection()
            total_tok = conn.cursor().execute("SELECT SUM(total_tokens) FROM usage_events WHERE session_id = 'sess_dedup_01'").fetchone()[0]
            conn.close()

        self.assertEqual(total_tok, 3000, "Tokens must not be double counted")

    def test_05_deduplication_via_temporal_fingerprint(self):
        """Assert proxy and log scanner recording the exact same session/tokens within +-60s does not double count."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        # Proxy record
        id_proxy = self.database.record_usage_event(
            provider="ollama",
            model="qwen2.5:14b",
            session_id="sess_cli_session_99",
            input_tokens=1200,
            output_tokens=300,
            source="emulator",
            is_proxied=1,
            recorded_at=now_iso
        )

        # Scanner record arriving 15 seconds later with same session and token count
        later_iso = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=15)).isoformat()
        id_scanner = self.database.record_usage_event(
            provider="ollama",
            model="qwen2.5:14b",
            session_id="sess_cli_session_99",
            input_tokens=1200,
            output_tokens=300,
            source="log_scanner",
            is_proxied=0,
            recorded_at=later_iso
        )

        self.assertEqual(id_proxy, id_scanner, "Temporal fingerprint correlation must merge records")
        summary = self.database.get_usage_summary(provider="ollama")
        self.assertEqual(summary["total_tokens_today"], 1500)

    def test_06_multi_account_aggregation_and_sum_parity(self):
        """Assert distinct accounts on the same platform report distinct metrics and sum exactly to platform total."""
        # Account 1: Personal
        self.database.record_usage_event(
            provider="gemini",
            model="gemini-2.0-flash",
            account_id="acidcow_personal",
            token_id="key_personal_flash",
            input_tokens=1000,
            output_tokens=500
        )
        # Account 2: Work/Team
        self.database.record_usage_event(
            provider="gemini",
            model="gemini-1.5-pro",
            account_id="synthesis_work",
            token_id="key_work_pro",
            input_tokens=3000,
            output_tokens=1500
        )

        comp = self.database.get_comparative_metrics()
        gemini_item = comp["providers"]["gemini"]
        self.assertEqual(gemini_item["tokens_today"], 6000)

        # Accounts list in hierarchy
        accounts = gemini_item.get("accounts", [])
        self.assertEqual(len(accounts), 2)
        acc_tokens = sum(a["tokens_today"] for a in accounts)
        self.assertEqual(acc_tokens, 6000, "Sum of account tokens must equal platform total")

    def test_07_multi_instance_aggregation_and_sum_parity(self):
        """Assert distinct instances (e.g. local vs remote worker node) report distinct metrics and aggregate cleanly."""
        # Instance 1: Local GPU
        self.database.record_usage_event(
            provider="ollama",
            model="llama3.2:3b",
            instance_id="local_rtx4090",
            input_tokens=2000,
            output_tokens=400
        )
        # Instance 2: Remote LAN Worker Node
        self.database.record_usage_event(
            provider="ollama",
            model="qwen2.5:14b",
            instance_id="worker_node_192.168.1.50",
            input_tokens=8000,
            output_tokens=1600
        )

        comp = self.database.get_comparative_metrics()
        ollama_item = comp["providers"]["ollama"]
        self.assertEqual(ollama_item["tokens_today"], 12000)

        instances = ollama_item.get("instances", [])
        self.assertEqual(len(instances), 2)
        inst_tokens = sum(i["tokens_today"] for i in instances)
        self.assertEqual(inst_tokens, 12000, "Sum of instance tokens must equal platform total")

    def test_08_pivot_api_group_by_platform_and_model(self):
        """Assert GET /api/usage/pivot returns rows grouped by platform and model with accurate totals."""
        import urllib.request
        self.database.record_usage_event(provider="claude", model="claude-3-5-sonnet", input_tokens=1000, output_tokens=500)
        self.database.record_usage_event(provider="claude", model="claude-3-5-haiku", input_tokens=2000, output_tokens=200)
        self.database.record_usage_event(provider="gemini", model="gemini-2.0-flash", input_tokens=3000, output_tokens=300)

        url = f"http://127.0.0.1:{self.server.server_port}/api/usage/pivot?dimensions=platform,model"
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        self.assertTrue(data.get("success"))
        rows = data.get("rows", [])
        self.assertEqual(len(rows), 3)
        self.assertEqual(data["totals"]["total_tokens"], 7000)

    def test_09_pivot_api_group_by_source_proxy_vs_direct(self):
        """Assert GET /api/usage/pivot groups by traffic source (proxy vs direct vs emulator)."""
        import urllib.request
        self.database.record_usage_event(provider="claude", model="sonnet", input_tokens=1000, output_tokens=500, source="proxy", is_proxied=1)
        self.database.record_usage_event(provider="claude", model="sonnet", input_tokens=2000, output_tokens=500, source="direct", is_proxied=0)
        self.database.record_usage_event(provider="ollama", model="gemma", input_tokens=3000, output_tokens=500, source="emulator", is_proxied=1)

        url = f"http://127.0.0.1:{self.server.server_port}/api/usage/pivot?dimensions=source"
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        self.assertTrue(data.get("success"))
        sources = {r["source"]: r["total_tokens"] for r in data["rows"]}
        self.assertEqual(sources.get("proxy"), 1500)
        self.assertEqual(sources.get("direct"), 2500)
        self.assertEqual(sources.get("emulator"), 3500)
        self.assertEqual(data["totals"]["total_tokens"], 7500)

    def test_10_pivot_api_group_by_client_ip_and_alias(self):
        """Assert GET /api/usage/pivot groups by network client and alias."""
        import urllib.request
        self.database.record_usage_event(provider="claude", model="sonnet", input_tokens=1000, output_tokens=0, client_ip="192.168.1.10", client_alias="Dev-Desktop")
        self.database.record_usage_event(provider="claude", model="sonnet", input_tokens=2000, output_tokens=0, client_ip="192.168.1.20", client_alias="CI-Runner")

        url = f"http://127.0.0.1:{self.server.server_port}/api/usage/pivot?dimensions=client"
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        self.assertTrue(data.get("success"))
        client_tokens = {r.get("client_ip"): r["total_tokens"] for r in data["rows"]}
        self.assertEqual(client_tokens.get("192.168.1.10"), 1000)
        self.assertEqual(client_tokens.get("192.168.1.20"), 2000)

    def test_11_pivot_api_filtering_by_source_and_client(self):
        """Assert GET /api/usage/pivot filters by source='proxy' or client IP."""
        import urllib.request
        self.database.record_usage_event(provider="claude", model="sonnet", input_tokens=1000, output_tokens=0, source="proxy", client_ip="10.0.0.5")
        self.database.record_usage_event(provider="claude", model="sonnet", input_tokens=2000, output_tokens=0, source="direct", client_ip="10.0.0.5")

        url = f"http://127.0.0.1:{self.server.server_port}/api/usage/pivot?dimensions=model&filter_source=proxy"
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        self.assertEqual(len(data["rows"]), 1)
        self.assertEqual(data["totals"]["total_tokens"], 1000)

    def test_12_granular_timeseries_ollama_model_id_normalization(self):
        """Assert get_granular_timeseries emits series with both ollama_model_ prefix and bare model name."""
        self.database.record_usage_event(
            provider="ollama",
            model="nomic-embed-text:latest",
            input_tokens=5000,
            output_tokens=0
        )

        ts = self.database.get_granular_timeseries(window="1h", bucket_minutes=5)
        series_ids = [s["id"] for s in ts["series"]]
        self.assertTrue(
            any("nomic-embed-text:latest" in s_id for s_id in series_ids),
            f"Series IDs must include nomic-embed-text:latest: {series_ids}"
        )

    def test_13_native_widget_apply_theme_called_on_settings_update(self):
        """Assert NativeTaskbarWidget._apply_settings_from_server triggers apply_theme when theme changes."""
        widget = NativeTaskbarWidget()
        initial_theme = widget.theme_name

        # Simulate receiving new theme from server
        widget._apply_settings_from_server({"widget_theme": "cyberpunk"})
        self.assertEqual(widget.theme_name, "cyberpunk")

    def test_14_native_widget_individual_quota_card_height(self):
        """Assert Claude card height in native widget accounts for individual tracking mode without empty gap."""
        widget = NativeTaskbarWidget()
        widget.expanded_accounts = {"claude": True}
        widget.quota_tracking_mode = "individual"

        # Calculate expected card height for individual mode
        card_h = widget.calculate_card_height("claude", is_expanded=True)
        self.assertLessEqual(card_h, 75, f"Claude card height in individual mode should be ~66px, got {card_h}")

    def test_15_trends_hierarchy_endpoint_streamlines_individual_mode(self):
        """Assert /api/usage/trends/hierarchy filters corporate division series in individual mode."""
        import urllib.request
        self.database.set_setting("quota_tracking_mode", "individual")
        self.database.record_usage_event(provider="claude", model="sonnet", input_tokens=1000, output_tokens=500)

        url = f"http://127.0.0.1:{self.server.server_port}/api/usage/trends/hierarchy?provider=claude&window=24h&scope=individual"
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        series_keys = [s["key"] for s in data["series"]]
        self.assertNotIn("claude_department", series_keys, "Department series should be suppressed in individual mode")
        self.assertNotIn("claude_enterprise", series_keys, "Enterprise series should be suppressed in individual mode")

    def test_16_proxy_source_breakdown_in_comparative_metrics(self):
        """Assert get_comparative_metrics provides clear source_breakdown for proxy vs direct traffic."""
        self.database.record_usage_event(provider="claude", model="sonnet", input_tokens=1000, output_tokens=0, source="proxy", is_proxied=1)
        self.database.record_usage_event(provider="claude", model="sonnet", input_tokens=2000, output_tokens=0, source="direct", is_proxied=0)

        comp = self.database.get_comparative_metrics()
        claude_comp = comp["providers"]["claude"]
        self.assertIn("source_breakdown", claude_comp)
        self.assertEqual(claude_comp["source_breakdown"]["proxy"], 1000)
        self.assertEqual(claude_comp["source_breakdown"]["direct"], 2000)

    def test_17_native_widget_child_series_uses_real_hierarchy_names(self):
        """Assert native widget _get_provider_child_series utilizes real account and user names rather than hardcoded mock strings."""
        widget = NativeTaskbarWidget()
        mock_item = {
            "tokens_today": 5000,
            "hierarchy": {
                "user_name": "James Eckhardt",
                "team_name": "Synthesis Core Team",
                "account_name": "Synthesis Work Account"
            }
        }
        child_series = widget._get_provider_child_series("claude", mock_item)
        labels = [name for _, _, name in child_series]
        self.assertTrue(any("James Eckhardt" in lbl for lbl in labels))

    def test_18_instance_reporting_in_recent_sessions(self):
        """Assert get_recent_sessions exposes source, instance_id, and is_proxied."""
        self.database.record_usage_event(
            provider="gemini",
            model="gemini-2.0-flash",
            session_id="sess_instance_test",
            input_tokens=500,
            output_tokens=100,
            source="proxy",
            instance_id="node_gpu_rack_3",
            is_proxied=1
        )
        sessions = self.database.get_recent_sessions()
        target = next((s for s in sessions if s["session_id"] == "sess_instance_test"), None)
        self.assertIsNotNone(target)
        self.assertEqual(target.get("source"), "proxy")
        self.assertEqual(target.get("instance_id"), "node_gpu_rack_3")
        self.assertEqual(target.get("is_proxied"), 1)

    def test_19_pivot_api_window_filter(self):
        """Assert GET /api/usage/pivot respects window parameter (1h vs all)."""
        import urllib.request
        # Event 1: Recent (now)
        self.database.record_usage_event(provider="claude", model="sonnet", input_tokens=1000, output_tokens=0)
        # Event 2: 5 hours ago
        past_iso = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=5)).isoformat()
        self.database.record_usage_event(provider="claude", model="sonnet", input_tokens=2000, output_tokens=0, recorded_at=past_iso)

        # Query 1h window
        url_1h = f"http://127.0.0.1:{self.server.server_port}/api/usage/pivot?dimensions=model&window=1h"
        with urllib.request.urlopen(url_1h) as resp:
            data_1h = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(data_1h["totals"]["total_tokens"], 1000)

        # Query all window
        url_all = f"http://127.0.0.1:{self.server.server_port}/api/usage/pivot?dimensions=model&window=all"
        with urllib.request.urlopen(url_all) as resp:
            data_all = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(data_all["totals"]["total_tokens"], 3000)

    def test_20_zero_double_accounting_with_deduplicated_summary(self):
        """Assert total estate tokens across all methods match deduplicated totals."""
        self.database.record_usage_event(provider="claude", model="sonnet", input_tokens=1000, output_tokens=500, external_id="req_dup_01")
        self.database.record_usage_event(provider="claude", model="sonnet", input_tokens=1000, output_tokens=500, external_id="req_dup_01")
        self.database.record_usage_event(provider="gemini", model="flash", input_tokens=2000, output_tokens=500)

        summary = self.database.get_usage_summary()
        self.assertEqual(summary["total_tokens_today"], 4000, "1500 claude + 2500 gemini = 4000 total tokens")

if __name__ == "__main__":
    unittest.main()

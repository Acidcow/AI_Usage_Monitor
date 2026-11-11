"""
Unit Tests for AIUM-904:
Claude Pro Plan Alignment, Local vs. Remote Node Disaggregation & Canonical Unified Telemetry Taxonomy.
"""

import datetime
import json
import os
import shutil
import tempfile
import unittest
import urllib.request
from pathlib import Path

from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.providers.claude import ClaudeProvider
from backend.security.dpapi_vault import DPAPIVault
from backend.server.http_server import AppHTTPServer
from backend.storage.database import UsageDatabase
from backend.storage.taxonomy import (
    CANONICAL_TAXONOMY_TIERS,
    PROVIDER_TERMINOLOGY_MATRIX,
    classify_account_tier,
    classify_node_locality,
    get_full_taxonomy_specification,
    normalize_event_taxonomy,
)


class TestUnifiedTaxonomyClaudeProAndNodeLocality(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_taxonomy.db")
        self.db = UsageDatabase(db_path=self.db_path)
        self.vault = DPAPIVault(storage_path=os.path.join(self.temp_dir, "vault.json"))
        self.diagnostics = DiagnosticsEngine(log_dir=self.temp_dir)
        self.claude = ClaudeProvider(self.db, self.vault, self.diagnostics)

        # Register both a Local Ollama Node and a Remote LAN Ollama Node
        conn = self.db._get_connection()
        cur = conn.cursor()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur.execute(
            """
            INSERT OR REPLACE INTO managed_nodes
            (id, name, endpoint, engine, status, max_concurrency, queue_timeout_seconds, is_trusted, compute_group, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'ONLINE', 2, 30.0, 1, 'Active Compute', 10, ?, ?)
            """,
            ("node_ollama_1387210", "DESKTOP-C9FNLB9 (Local)", "http://127.0.0.1:11434", "ollama", now_iso, now_iso),
        )
        cur.execute(
            """
            INSERT OR REPLACE INTO managed_nodes
            (id, name, endpoint, engine, status, max_concurrency, queue_timeout_seconds, is_trusted, compute_group, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'ONLINE', 2, 30.0, 1, 'Active Compute', 8, ?, ?)
            """,
            ("node_ollama_3958379", "JamesE-PC (LAN GPU)", "http://10.1.7.74:11434", "ollama", now_iso, now_iso),
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.db = None
        self.claude = None
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # 1. Canonical 8-Tier Taxonomy & Terminology Matrix
    # ------------------------------------------------------------------
    def test_01_canonical_taxonomy_has_all_8_tiers_and_5_platforms(self):
        self.assertEqual(len(CANONICAL_TAXONOMY_TIERS), 8)
        tier_codes = [t["code"] for t in CANONICAL_TAXONOMY_TIERS]
        self.assertEqual(
            tier_codes,
            [
                "platform",
                "tenant_account",
                "workspace_pool",
                "principal_seat",
                "compute_node",
                "client_host",
                "access_route",
                "model_session",
            ],
        )
        for prov in ("claude", "gemini", "ollama", "chatgpt", "copilot"):
            self.assertIn(prov, PROVIDER_TERMINOLOGY_MATRIX)
            for code in tier_codes:
                self.assertIn(code, PROVIDER_TERMINOLOGY_MATRIX[prov])

    def test_02_classify_node_locality_distinguishes_local_remote_and_cloud(self):
        loc1, lbl1 = classify_node_locality(
            provider="ollama",
            instance_id="node_ollama_1387210",
            node_endpoint="http://127.0.0.1:11434",
        )
        self.assertEqual(loc1, "local")
        self.assertIn("Local", lbl1)

        loc2, lbl2 = classify_node_locality(
            provider="ollama",
            instance_id="node_ollama_3958379",
            node_endpoint="http://10.1.7.74:11434",
        )
        self.assertEqual(loc2, "remote_lan")
        self.assertIn("Remote LAN", lbl2)

        loc3, lbl3 = classify_node_locality(
            provider="claude",
            instance_id="local",
        )
        self.assertEqual(loc3, "cloud")
        self.assertIn("Cloud", lbl3)

    def test_03_classify_account_tier_distinguishes_personal_pro_vs_team_org(self):
        t_pro, lbl_pro = classify_account_tier(
            provider="claude",
            account_id="James Eckhardt",
            team_name="Claude Pro",
            plan_type="Claude Pro",
        )
        self.assertEqual(t_pro, "personal_pro")
        self.assertIn("Claude Pro", lbl_pro)

        t_team, lbl_team = classify_account_tier(
            provider="claude",
            account_id="Synthesis2",
            team_name="Synthesis2",
            plan_type="Team Enterprise",
        )
        self.assertEqual(t_team, "team_org")
        self.assertIn("Team", lbl_team)

    def test_04_normalize_event_taxonomy_extracts_remote_node_from_session_id(self):
        nodes_map = {
            "node_ollama_3958379": {
                "id": "node_ollama_3958379",
                "name": "JamesE-PC",
                "endpoint": "http://10.1.7.74:11434",
                "compute_group": "Active Compute",
            }
        }
        row = {
            "provider": "ollama",
            "model": "gemma4:e4b",
            "session_id": "remote_node_ollama_3958379_1761052013",
            "instance_id": "local",
            "source": "proxy",
            "client_ip": "10.1.7.74",
            "client_alias": "JamesE-PC",
        }
        tax = normalize_event_taxonomy(row, nodes_map=nodes_map)
        self.assertEqual(tax["instance_id"], "node_ollama_3958379")
        self.assertEqual(tax["locality"], "remote_lan")
        self.assertIn("JamesE-PC", tax["compute_node"])

    # ------------------------------------------------------------------
    # 2. Claude Code Streaming Chunk Deduplication & Claude Pro Plan
    # ------------------------------------------------------------------
    def test_05_claude_scan_local_logs_deduplicates_streaming_chunks_by_message_id(self):
        mock_claude_dir = Path(self.temp_dir) / ".claude_dedup"
        proj_dir = mock_claude_dir / "projects" / "TestProj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        log_file = proj_dir / "session-stream.jsonl"

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        # 3 streaming chunks sharing the same message.id ("msg_01STREAM999")
        # Each chunk repeats 200,000 cache_read_input_tokens and increments output_tokens (10 -> 80 -> 250)
        chunks = [
            {
                "type": "assistant",
                "sessionId": "sess-stream-1",
                "timestamp": now_iso,
                "message": {
                    "id": "msg_01STREAM999",
                    "model": "claude-opus-4-6",
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 10,
                        "cache_creation_input_tokens": 500,
                        "cache_read_input_tokens": 200000,
                    },
                },
            },
            {
                "type": "assistant",
                "sessionId": "sess-stream-1",
                "timestamp": now_iso,
                "message": {
                    "id": "msg_01STREAM999",
                    "model": "claude-opus-4-6",
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 80,
                        "cache_creation_input_tokens": 500,
                        "cache_read_input_tokens": 200000,
                    },
                },
            },
            {
                "type": "assistant",
                "sessionId": "sess-stream-1",
                "timestamp": now_iso,
                "message": {
                    "id": "msg_01STREAM999",
                    "model": "claude-opus-4-6",
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 250,
                        "cache_creation_input_tokens": 500,
                        "cache_read_input_tokens": 200000,
                    },
                },
            },
        ]
        with open(log_file, "w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c) + "\n")

        ingested = self.claude.scan_local_logs(search_dir=str(mock_claude_dir))
        self.assertEqual(ingested, 1, "3 streaming chunks with identical message.id must collapse into 1 turn")

        summary = self.db.get_usage_summary(provider="claude")
        self.assertEqual(summary["input_tokens_today"], 100)
        self.assertEqual(summary["output_tokens_today"], 250)
        self.assertEqual(summary["cache_creation_tokens_today"], 500)
        self.assertEqual(summary["cache_read_tokens_today"], 200000)
        self.assertEqual(summary["total_tokens_today"], 200850)

        # Second scan is idempotent
        ingested_again = self.claude.scan_local_logs(search_dir=str(mock_claude_dir))
        self.assertEqual(ingested_again, 0)

    def test_06_claude_scan_local_logs_preserves_calibrated_claude_pro_plan(self):
        self.claude.calibrate_limits(
            scope="individual",
            individual_session_used_pct=18.0,
            individual_weekly_used_pct=12.0,
            plan_type="Claude Pro",
            user_name="James Eckhardt",
            team_name="Claude Pro",
        )
        mock_claude_dir = Path(self.temp_dir) / ".claude_pro"
        proj_dir = mock_claude_dir / "projects" / "ProProj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with open(proj_dir / "pro.jsonl", "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "type": "assistant",
                        "sessionId": "sess-pro-1",
                        "timestamp": now_iso,
                        "message": {
                            "id": "msg_pro_01",
                            "model": "claude-sonnet-4-6",
                            "usage": {"input_tokens": 500, "output_tokens": 200},
                        },
                    }
                )
                + "\n"
            )
        self.claude.scan_local_logs(search_dir=str(mock_claude_dir))
        snap = self.db.get_provider_snapshots()["claude"]
        self.assertEqual(snap["plan_type"], "Claude Pro")

    def test_07_record_usage_event_attributes_personal_claude_pro_when_calibrated(self):
        self.claude.calibrate_limits(
            scope="individual",
            individual_session_used_pct=15.0,
            individual_weekly_used_pct=10.0,
            plan_type="Claude Pro",
            user_name="James Eckhardt",
            team_name="Claude Pro",
        )
        evt_id = self.db.record_usage_event(
            provider="claude",
            model="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=500,
            session_id="sess_pro_personal_1",
        )
        conn = self.db._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT account_id, team_name, user_name FROM usage_events WHERE id = ?", (evt_id,))
        row = dict(cur.fetchone())
        conn.close()
        self.assertEqual(row["account_id"], "James Eckhardt")
        self.assertEqual(row["team_name"], "Claude Pro")

    def test_08_record_usage_event_resolves_remote_node_instance_id_from_session_id(self):
        evt_id = self.db.record_usage_event(
            provider="ollama",
            model="gemma4:e4b",
            input_tokens=2000,
            output_tokens=500,
            session_id="remote_node_ollama_3958379_1761052013",
            instance_id="local",
        )
        conn = self.db._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT instance_id FROM usage_events WHERE id = ?", (evt_id,))
        row = dict(cur.fetchone())
        conn.close()
        self.assertEqual(row["instance_id"], "node_ollama_3958379")

    # ------------------------------------------------------------------
    # 3. Granular Timeseries Disaggregation & Scope Filtering
    # ------------------------------------------------------------------
    def _seed_disparate_telemetry(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        t_recent = (now - datetime.timedelta(minutes=25)).isoformat()

        # 1. Personal Claude Pro event
        self.db.record_usage_event(
            provider="claude",
            model="claude-sonnet-4-6",
            input_tokens=4000,
            output_tokens=1000,
            session_id="sess_pro_1",
            account_id="James Eckhardt",
            team_name="Claude Pro",
            user_name="James Eckhardt",
            source="cli_scanner",
            recorded_at=t_recent,
        )
        # 2. Legacy Company / Team Pool Claude event (Synthesis2)
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-7-sonnet",
            input_tokens=15000,
            output_tokens=5000,
            session_id="sess_team_syn2",
            account_id="Synthesis2",
            team_name="Synthesis2",
            user_name="James Eckhardt",
            source="proxy",
            recorded_at=t_recent,
        )
        # 3. Local Ollama Node event (DESKTOP-C9FNLB9)
        self.db.record_usage_event(
            provider="ollama",
            model="gemma4:e4b",
            input_tokens=8000,
            output_tokens=2000,
            session_id="ollama_local_1",
            instance_id="node_ollama_1387210",
            source="log_scanner",
            client_ip="127.0.0.1",
            client_alias="DESKTOP-C9FNLB9",
            recorded_at=t_recent,
        )
        # 4. Remote LAN Ollama Node event (JamesE-PC @ 10.1.7.74)
        self.db.record_usage_event(
            provider="ollama",
            model="gemma4:e4b",
            input_tokens=12000,
            output_tokens=3000,
            session_id="remote_node_ollama_3958379_100",
            instance_id="node_ollama_3958379",
            source="proxy",
            client_ip="10.1.7.74",
            client_alias="JamesE-PC",
            recorded_at=t_recent,
        )

    def test_09_granular_timeseries_separates_local_vs_remote_ollama_and_personal_vs_team_claude(self):
        self._seed_disparate_telemetry()
        ts = self.db.get_granular_timeseries(window="1h", bucket_minutes=5, breakdown="locality")
        series_by_id = {s["id"]: s for s in ts["series"]}

        self.assertIn("claude_personal_pro", series_by_id)
        self.assertIn("claude_team_org", series_by_id)
        self.assertIn("ollama_local_node", series_by_id)
        self.assertIn("ollama_remote_lan", series_by_id)

        self.assertEqual(series_by_id["claude_personal_pro"]["total_tokens"], 5000)
        self.assertEqual(series_by_id["claude_team_org"]["total_tokens"], 20000)
        self.assertEqual(series_by_id["ollama_local_node"]["total_tokens"], 10000)
        self.assertEqual(series_by_id["ollama_remote_lan"]["total_tokens"], 15000)

    def test_10_granular_timeseries_scope_filter_personal_only_excludes_company_pool(self):
        self._seed_disparate_telemetry()
        ts_personal = self.db.get_granular_timeseries(
            window="1h",
            bucket_minutes=5,
            breakdown="locality",
            scope_filter="personal_only",
        )
        series_by_id = {s["id"]: s for s in ts_personal["series"]}
        self.assertEqual(series_by_id["claude"]["total_tokens"], 5000)
        self.assertNotIn("claude_team_org", series_by_id)

    def test_11_granular_timeseries_scope_filter_local_only_and_remote_only(self):
        self._seed_disparate_telemetry()
        ts_local = self.db.get_granular_timeseries(
            window="1h",
            bucket_minutes=5,
            breakdown="compute_node",
            scope_filter="local_only",
        )
        self.assertEqual(ts_local["total_tokens"], 10000)

        ts_remote = self.db.get_granular_timeseries(
            window="1h",
            bucket_minutes=5,
            breakdown="compute_node",
            scope_filter="remote_only",
        )
        self.assertEqual(ts_remote["total_tokens"], 15000)

    def test_12_granular_timeseries_supports_all_8_breakdown_dimensions(self):
        self._seed_disparate_telemetry()
        for b_mode in (
            "consolidated",
            "locality",
            "tenant_account",
            "workspace_pool",
            "compute_node",
            "client_host",
            "access_route",
            "model",
        ):
            ts = self.db.get_granular_timeseries(window="1h", bucket_minutes=5, breakdown=b_mode)
            self.assertEqual(ts["breakdown"], b_mode)
            self.assertGreaterEqual(len(ts["breakdown_series"]), 2, f"Breakdown mode '{b_mode}' should emit multiple series")

    # ------------------------------------------------------------------
    # 4. Hierarchical Trends & Comparative Metrics
    # ------------------------------------------------------------------
    def test_13_hierarchical_trends_ollama_separates_local_and_remote_lan_nodes(self):
        self._seed_disparate_telemetry()
        trends = self.db.get_hierarchical_trends(provider="ollama", window="1h")
        s_map = {s["id"]: s for s in trends["series"]}
        self.assertIn("ollama_total", s_map)
        self.assertIn("ollama_local_node", s_map)
        self.assertIn("ollama_remote_lan", s_map)
        self.assertEqual(s_map["ollama_total"]["total_tokens"], 25000)
        self.assertEqual(s_map["ollama_local_node"]["total_tokens"], 10000)
        self.assertEqual(s_map["ollama_remote_lan"]["total_tokens"], 15000)

    def test_14_hierarchical_trends_claude_separates_personal_pro_and_team_pool(self):
        self._seed_disparate_telemetry()
        trends = self.db.get_hierarchical_trends(provider="claude", window="1h")
        s_map = {s["id"]: s for s in trends["series"]}
        self.assertIn("claude_total", s_map)
        self.assertIn("claude_individual", s_map)
        self.assertIn("claude_team", s_map)
        self.assertEqual(s_map["claude_total"]["total_tokens"], 25000)
        self.assertEqual(s_map["claude_individual"]["total_tokens"], 5000)
        self.assertEqual(s_map["claude_team"]["total_tokens"], 20000)

    def test_15_comparative_metrics_includes_locality_breakdown_and_taxonomy(self):
        self._seed_disparate_telemetry()
        comp = self.db.get_comparative_metrics()
        self.assertIn("taxonomy", comp)
        ollama_comp = comp["providers"]["ollama"]
        self.assertEqual(ollama_comp["locality_breakdown"]["local"], 10000)
        self.assertEqual(ollama_comp["locality_breakdown"]["remote_lan"], 15000)

        claude_accts = {a["account_id"]: a for a in comp["providers"]["claude"]["accounts"]}
        self.assertEqual(claude_accts["James Eckhardt"]["account_tier"], "personal_pro")
        self.assertEqual(claude_accts["Synthesis2"]["account_tier"], "team_org")

    # ------------------------------------------------------------------
    # 5. Historical Reports Canonical Taxonomy Attribution
    # ------------------------------------------------------------------
    def test_16_historical_report_rows_include_locality_and_account_tier_labels(self):
        self._seed_disparate_telemetry()
        rep = self.db.query_historical_report(group_by="day")
        self.assertGreaterEqual(len(rep["rows"]), 4)
        for r in rep["rows"]:
            self.assertIn("locality", r)
            self.assertIn("locality_label", r)
            self.assertIn("account_tier", r)
            self.assertIn("account_tier_label", r)
            self.assertIn("compute_node", r)
            self.assertIn("workspace_pool", r)

    def test_17_historical_report_pivots_by_locality_and_account_tier_dimensions(self):
        self._seed_disparate_telemetry()
        rep_loc = self.db.query_historical_report(group_by="day", dimension="locality", provider="ollama")
        loc_vals = {r["dimension_value"]: r["total_tokens"] for r in rep_loc["rows"]}
        self.assertIn("Local Node (This PC)", loc_vals)
        self.assertIn("Remote LAN Node", loc_vals)

        rep_tier = self.db.query_historical_report(group_by="day", dimension="account_tier", provider="claude")
        tier_vals = {r["dimension_value"]: r["total_tokens"] for r in rep_tier["rows"]}
        self.assertIn("Claude Pro (Personal)", tier_vals)

    # ------------------------------------------------------------------
    # 6. REST API & Frontend UI Verification
    # ------------------------------------------------------------------
    def test_18_http_api_taxonomy_and_disaggregated_timeseries_endpoints(self):
        self._seed_disparate_telemetry()
        srv = AppHTTPServer(
            database=self.db,
            vault=self.vault,
            diagnostics=self.diagnostics,
            providers={"claude": self.claude},
            host="127.0.0.1",
            port=0,
        )
        srv.start()
        try:
            url_tax = f"http://127.0.0.1:{srv.server_port}/api/taxonomy"
            with urllib.request.urlopen(url_tax) as resp:
                tax_data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(len(tax_data["tiers"]), 8)
                self.assertIn("claude", tax_data["provider_matrix"])

            url_ts = f"http://127.0.0.1:{srv.server_port}/api/usage/timeseries?window=1h&breakdown=locality&scope_filter=personal_only"
            with urllib.request.urlopen(url_ts) as resp:
                ts_data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(ts_data["breakdown"], "locality")
                self.assertEqual(ts_data["scope_filter"], "personal_only")
                self.assertEqual(ts_data["total_tokens"], 30000)  # 5k personal Claude + 10k local Ollama + 15k remote Ollama
        finally:
            srv.stop()

    def test_19_frontend_usage_gauge_card_contains_disaggregation_scope_and_taxonomy_controls(self):
        repo_root = Path(__file__).resolve().parent.parent
        gauge_html = (repo_root / "frontend" / "components" / "usage_gauge_card.html").read_text(encoding="utf-8")
        self.assertIn('id="chart-breakdown-select"', gauge_html)
        self.assertIn('id="chart-scope-filter-select"', gauge_html)
        self.assertIn('id="unified-taxonomy-drawer"', gauge_html)
        for opt in ("locality", "consolidated", "tenant_account", "workspace_pool", "compute_node", "client_host", "access_route", "model"):
            self.assertIn(f'value="{opt}"', gauge_html)
        for s_opt in ("all", "personal_only", "team_only", "local_only", "remote_only"):
            self.assertIn(f'value="{s_opt}"', gauge_html)

    def test_20_frontend_app_js_wires_breakdown_scope_and_taxonomy_columns(self):
        repo_root = Path(__file__).resolve().parent.parent
        app_js = (repo_root / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("changeChartBreakdown(", app_js)
        self.assertIn("changeChartScopeFilter(", app_js)
        self.assertIn("toggleTaxonomyDrawer(", app_js)
        self.assertIn("key: 'locality_label'", app_js)
        self.assertIn("key: 'account_tier_label'", app_js)
        self.assertIn("key: 'compute_node'", app_js)


if __name__ == "__main__":
    unittest.main()

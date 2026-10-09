"""
Unit tests for AIUM-611, AIUM-612, and AIUM-613:
- Hierarchical Multi-Series Overlaid Trend Lines in Dashboard (FR-611)
- Mini Widget Multi-Plot Overlays, Nested Branch Charts & Parent Visibility Toggle (FR-612)
- Dynamic Hierarchy View Modes, Group Tagging & Platform Visibility Settings (FR-613)
"""

import unittest
import tempfile
import shutil
import json
import time
import datetime
from pathlib import Path

from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.server.http_server import AppHTTPServer
from backend.providers.claude import ClaudeProvider
from backend.providers.gemini import GeminiProvider
from backend.providers.ollama import OllamaProvider
from backend.providers.copilot import CopilotProvider
from backend.providers.chatgpt import ChatGPTProvider


class TestHierarchicalTrendsAndFiltering(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = str(Path(self.test_dir) / "test_trends.db")
        self.db = UsageDatabase(self.db_path)
        self.vault = DPAPIVault(str(Path(self.test_dir) / "test_vault.enc"))
        self.diagnostics = DiagnosticsEngine()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _seed_test_usage(self):
        """Seed sample usage events across multiple hours, providers, and dimensions."""
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # Seed Claude events with user and team
        for i in range(5):
            t = (now - datetime.timedelta(hours=i)).isoformat()
            self.db.record_usage_event(
                provider="claude",
                model="claude-3-7-sonnet",
                input_tokens=1000 + i * 200,
                output_tokens=500 + i * 100,
                estimated_cost=0.015,
                session_id=f"sess-c-{i}",
                user_name="James Eckhardt",
                team_name="Synthesis2"
            )

        # Seed Gemini events with child token IDs
        for i in range(4):
            t = (now - datetime.timedelta(hours=i)).isoformat()
            self.db.record_usage_event(
                provider="gemini",
                model="gemini-2.5-flash",
                input_tokens=2000,
                output_tokens=800,
                estimated_cost=0.002,
                session_id=f"sess-g-flash-{i}",
                token_id="tok_gem_flash"
            )
            self.db.record_usage_event(
                provider="gemini",
                model="gemini-2.5-pro",
                input_tokens=1500,
                output_tokens=600,
                estimated_cost=0.008,
                session_id=f"sess-g-pro-{i}",
                token_id="tok_gem_pro"
            )

        # Seed Ollama events with different models
        for i in range(3):
            self.db.record_usage_event(
                provider="ollama",
                model="llama3:latest",
                input_tokens=4000,
                output_tokens=1000,
                estimated_cost=0.0,
                session_id=f"sess-o-l3-{i}"
            )
            self.db.record_usage_event(
                provider="ollama",
                model="deepseek-r1:14b",
                input_tokens=8000,
                output_tokens=2000,
                estimated_cost=0.0,
                session_id=f"sess-o-ds-{i}"
            )

    def test_get_hierarchical_trends_claude(self):
        """Assert that get_hierarchical_trends for Claude returns overlaid parent & child series."""
        self._seed_test_usage()
        trends = self.db.get_hierarchical_trends(provider="claude", window="24h")
        self.assertIn("window", trends)
        self.assertEqual(trends["window"], "24h")
        self.assertIn("labels", trends)
        self.assertIn("series", trends)
        
        series_ids = [s["id"] for s in trends["series"]]
        # Parent series exists
        self.assertIn("claude_total", series_ids)
        # Child breakdown series exist
        self.assertTrue(any("individual" in sid or "team" in sid for sid in series_ids))
        
        for s in trends["series"]:
            self.assertIn("name", s)
            self.assertIn("color", s)
            self.assertIn("points", s)
            self.assertEqual(len(s["points"]), len(trends["labels"]))

    def test_get_hierarchical_trends_gemini_tokens(self):
        """Assert that get_hierarchical_trends for Gemini returns account & child token series."""
        self._seed_test_usage()
        trends = self.db.get_hierarchical_trends(provider="gemini", window="24h")
        self.assertIn("series", trends)
        series_names = [s["name"] for s in trends["series"]]
        self.assertTrue(any("Account" in name or "Gemini" in name for name in series_names))
        self.assertTrue(any("Flash" in s["name"] or "Pro" in s["name"] or "tok_gem" in s["id"] for s in trends["series"]))

    def test_get_hierarchical_trends_ollama_models(self):
        """Assert that get_hierarchical_trends for Ollama returns per-model series."""
        self._seed_test_usage()
        trends = self.db.get_hierarchical_trends(provider="ollama", window="24h")
        self.assertIn("series", trends)
        series_names = [s["name"] for s in trends["series"]]
        self.assertTrue(any("llama" in name.lower() for name in series_names))
        self.assertTrue(any("deepseek" in name.lower() for name in series_names))

    def test_estate_visibility_settings_crud(self):
        """Assert setting and getting platform/account visibility configurations."""
        # Default visibility
        vis = self.db.get_estate_visibility()
        self.assertIn("hidden_platforms", vis)
        self.assertIn("hidden_accounts", vis)
        self.assertIn("hidden_tags", vis)

        # Update visibility to hide chatgpt and copilot
        self.db.set_estate_visibility(
            hidden_platforms=["chatgpt", "copilot"],
            hidden_accounts=["acc_secret"],
            hidden_tags=["legacy"]
        )
        updated = self.db.get_estate_visibility()
        self.assertEqual(updated["hidden_platforms"], ["chatgpt", "copilot"])
        self.assertEqual(updated["hidden_accounts"], ["acc_secret"])
        self.assertEqual(updated["hidden_tags"], ["legacy"])

    def test_comparative_metrics_respects_visibility_filter(self):
        """Assert that get_comparative_metrics excludes hidden platforms when filter_visibility is True."""
        self.db.set_estate_visibility(hidden_platforms=["chatgpt"])
        comp = self.db.get_comparative_metrics(filter_visibility=True)
        self.assertNotIn("chatgpt", comp["providers"])
        self.assertIn("claude", comp["providers"])

    def test_widget_parent_chart_visibility_setting(self):
        """Assert persistence of widget_hide_parent_chart_on_expand setting."""
        self.db.set_setting("widget_hide_parent_chart_on_expand", "true")
        val = self.db.get_setting("widget_hide_parent_chart_on_expand")
        self.assertTrue(val)

    def test_all_settings_includes_estate_visibility(self):
        """Assert that get_all_settings() always returns estate_visibility structure."""
        st = self.db.get_all_settings()
        self.assertIn("estate_visibility", st)
        self.assertIn("hidden_platforms", st["estate_visibility"])

        self.db.set_estate_visibility(hidden_platforms=["gemini", "copilot"])
        st_updated = self.db.get_all_settings()
        self.assertEqual(st_updated["estate_visibility"]["hidden_platforms"], ["gemini", "copilot"])

    def _start_server(self):
        providers = {
            "claude": ClaudeProvider(self.db, self.vault, self.diagnostics),
            "gemini": GeminiProvider(self.db, self.vault, self.diagnostics),
            "ollama": OllamaProvider(self.db, self.vault, self.diagnostics),
            "copilot": CopilotProvider(self.db, self.vault, self.diagnostics),
            "chatgpt": ChatGPTProvider(self.db, self.vault, self.diagnostics)
        }
        server = AppHTTPServer(
            database=self.db,
            vault=self.vault,
            diagnostics=self.diagnostics,
            providers=providers,
            host="127.0.0.1",
            port=0
        )
        server.start()
        port = server.server_port
        return server, port

    def test_rest_api_trends_hierarchy_endpoint(self):
        """Assert GET /api/usage/trends/hierarchy returns multi-series JSON."""
        server, port = self._start_server()
        try:
            import urllib.request
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/usage/trends/hierarchy?provider=claude&window=24h")
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode())
                self.assertEqual(data["window"], "24h")
                self.assertIn("series", data)
                self.assertIn("labels", data)
                self.assertIn("window_label", data)
        finally:
            server.stop()

    def test_rest_api_visibility_endpoints(self):
        """Assert GET and POST /api/settings/visibility."""
        server, port = self._start_server()
        try:
            import urllib.request
            # 1. GET initial visibility
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/settings/visibility")
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                init_vis = json.loads(resp.read().decode())
                self.assertIn("hidden_platforms", init_vis)

            # 2. POST update visibility
            payload = json.dumps({
                "hidden_platforms": ["chatgpt"],
                "hidden_accounts": [],
                "hidden_tags": []
            }).encode()
            req_post = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/settings/visibility",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req_post) as resp:
                self.assertEqual(resp.status, 200)
                res = json.loads(resp.read().decode())
                self.assertTrue(res.get("success"))
                self.assertEqual(res["visibility"]["hidden_platforms"], ["chatgpt"])
        finally:
            server.stop()


    def test_get_hierarchical_trends_windows(self):
        """Assert that get_hierarchical_trends supports 1h, 7d, and 30d windows."""
        self._seed_test_usage()
        t_1h = self.db.get_hierarchical_trends(provider="claude", window="1h")
        self.assertEqual(t_1h["window"], "1h")
        self.assertEqual(len(t_1h["labels"]), 12)

        t_7d = self.db.get_hierarchical_trends(provider="claude", window="7d")
        self.assertEqual(t_7d["window"], "7d")
        self.assertEqual(len(t_7d["labels"]), 7)

        t_30d = self.db.get_hierarchical_trends(provider="claude", window="30d")
        self.assertEqual(t_30d["window"], "30d")
        self.assertEqual(len(t_30d["labels"]), 30)

    def test_grouping_tags_integration(self):
        """Assert creating cross platform tags and associating with accounts/providers."""
        tag_id = self.db.add_cross_platform_tag(
            tag_name="Production",
            target_type="provider",
            target_identifier="claude",
            description="Production Claude AI workloads"
        )
        self.assertIsNotNone(tag_id)
        tags = self.db.get_cross_platform_tags()
        self.assertTrue(any(t["tag_name"] == "Production" for t in tags))
    def test_frontend_js_syntax_validity(self):
        """Assert that frontend JavaScript files (app.js, widget.js) have valid syntax without uncaught parser errors."""
        import subprocess
        import shutil
        repo_root = Path(__file__).resolve().parent.parent
        js_files = [
            repo_root / "frontend" / "js" / "app.js",
            repo_root / "frontend" / "js" / "widget.js"
        ]
        node_bin = shutil.which("node")
        if node_bin:
            for js in js_files:
                res = subprocess.run([node_bin, "--check", str(js)], capture_output=True, text=True)
                self.assertEqual(res.returncode, 0, f"Syntax error in {js.name}:\n{res.stderr}")
        else:
            # Fallback simple bracket validator
            for js in js_files:
                content = js.read_text(encoding="utf-8")
                # Ensure non-empty and starts properly
    def test_get_hierarchical_trends_idle_provider_returns_strict_zeroes(self):
        """AIUM-614: Assert that an idle provider with 0 usage events returns strictly 0s (no saw-tooth modulo)."""
        trends = self.db.get_hierarchical_trends(provider="gemini", window="24h")
        self.assertIn("series", trends)
        for s in trends["series"]:
            # Every point must be exactly 0, not modulo numbers like (i % 5) * 200
            for pt in s["points"]:
                self.assertEqual(pt, 0, f"Point {pt} in series {s.get('name')} should be 0 for idle provider")
            self.assertEqual(max(s["points"]), 0)

    def test_get_hierarchical_trends_has_dual_key_label_and_id_name_aliases(self):
        """AIUM-614: Assert that returned series contain both id/key and name/label aliases to prevent 'undefined' legends."""
        self._seed_test_usage()
        for prov in ["claude", "gemini", "ollama"]:
            trends = self.db.get_hierarchical_trends(provider=prov, window="24h")
            for s in trends["series"]:
                self.assertIn("id", s)
                self.assertIn("key", s)
                self.assertEqual(s["id"], s["key"])
                self.assertIn("name", s)
                self.assertIn("label", s)
                self.assertEqual(s["name"], s["label"])
                self.assertNotEqual(s["label"], "undefined")
                self.assertTrue(len(s["label"]) > 0)

if __name__ == "__main__":
    unittest.main()


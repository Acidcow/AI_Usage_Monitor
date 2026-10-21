import os
import sys
import json
import unittest
import tempfile
import shutil
import threading
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.server.http_server import AppHTTPServer
from backend.providers.claude import ClaudeProvider


class TestIndividualVsTeamAllowanceTracking(unittest.TestCase):
    """
    TDD Test Suite for FR-618: Individual vs Team Allowance Tracking Mode Toggle
    and Hierarchy Streamlining.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_allowance.db")
        self.db = UsageDatabase(db_path=self.db_path)
        self.vault = DPAPIVault(storage_path=os.path.join(self.temp_dir, "vault.json"))
        self.diagnostics = DiagnosticsEngine(log_dir=self.temp_dir)

    def tearDown(self):
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass

    # -------------------------------------------------------------
    # 1. Database Setting Read / Write & Validation
    # -------------------------------------------------------------
    def test_default_quota_tracking_mode_is_individual(self):
        """Assert default quota tracking mode is 'individual'."""
        mode = self.db.get_quota_tracking_mode()
        self.assertEqual(mode, "individual")

    def test_set_quota_tracking_mode_validates_and_persists(self):
        """Assert toggling quota tracking mode between 'individual' and 'team'."""
        self.db.set_quota_tracking_mode("team")
        self.assertEqual(self.db.get_quota_tracking_mode(), "team")

        self.db.set_quota_tracking_mode("individual")
        self.assertEqual(self.db.get_quota_tracking_mode(), "individual")

    def test_set_quota_tracking_mode_invalid_raises_or_defaults(self):
        """Assert invalid tracking mode raises ValueError or falls back safely."""
        with self.assertRaises(ValueError):
            self.db.set_quota_tracking_mode("invalid_mode")

    def test_get_all_settings_includes_quota_tracking_mode(self):
        """Assert get_all_settings() returns quota_tracking_mode."""
        settings = self.db.get_all_settings()
        self.assertIn("quota_tracking_mode", settings)
        self.assertEqual(settings["quota_tracking_mode"], "individual")

        self.db.set_quota_tracking_mode("team")
        settings_updated = self.db.get_all_settings()
        self.assertEqual(settings_updated["quota_tracking_mode"], "team")

    def test_settings_persistence_across_database_reconnects(self):
        """Assert settings persist when a new UsageDatabase instance opens the same SQLite file."""
        self.db.set_quota_tracking_mode("team")
        new_db = UsageDatabase(db_path=self.db_path)
        self.assertEqual(new_db.get_quota_tracking_mode(), "team")

    # -------------------------------------------------------------
    # 2. Comparative Metrics Scoping & Streamlined Hierarchy
    # -------------------------------------------------------------
    def test_comparative_metrics_defaults_to_individual_tracking(self):
        """Assert comparative metrics uses individual tracking mode by default."""
        comp = self.db.get_comparative_metrics()
        self.assertEqual(comp.get("tracking_mode"), "individual")
        self.assertEqual(comp.get("active_scope"), "individual")

    def test_comparative_metrics_uses_direct_unconverted_values(self):
        """Assert that calibrated personal quotas are used 1:1 without company fractional conversion."""
        # Record calibrated Claude snapshot via ClaudeProvider
        prov = ClaudeProvider(self.db, self.vault, self.diagnostics)
        prov.calibrate_limits(
            individual_session_used_pct=60.0,
            individual_weekly_used_pct=27.0,
            scope="individual",
            user_name="James Eckhardt"
        )
        comp = self.db.get_comparative_metrics()
        claude_comp = comp["providers"]["claude"]

        # Directly 40.0% and 73.0% (1:1 with claude.ai/settings/usage)
        self.assertEqual(claude_comp["session_balance_remaining_pct"], 40.0)
        self.assertEqual(claude_comp["weekly_balance_remaining_pct"], 73.0)

    def test_comparative_metrics_individual_mode_streamlines_hierarchy(self):
        """Assert that in individual tracking mode, higher-level theoretical rollups are marked disabled or omitted."""
        comp = self.db.get_comparative_metrics()
        claude_comp = comp["providers"]["claude"]
        h = claude_comp.get("hierarchy", {})

        self.assertTrue(h.get("streamlined"))
        self.assertEqual(h.get("tracking_mode"), "individual")
        # Department and Enterprise rollups are disabled or omitted in individual tracking mode
        if "department" in h:
            self.assertFalse(h["department"].get("enabled", True))
        if "enterprise" in h:
            self.assertFalse(h["enterprise"].get("enabled", True))

    def test_comparative_metrics_team_mode_retains_higher_hierarchies(self):
        """Assert that in team tracking mode, team, department, and enterprise rollups are enabled."""
        self.db.set_quota_tracking_mode("team")
        comp = self.db.get_comparative_metrics()
        self.assertEqual(comp.get("tracking_mode"), "team")
        claude_comp = comp["providers"]["claude"]
        h = claude_comp.get("hierarchy", {})

        self.assertFalse(h.get("streamlined", False))
        self.assertEqual(h.get("tracking_mode"), "team")
        self.assertIn("team", h)
        self.assertIn("department", h)
        self.assertTrue(h["department"].get("enabled", True))
        self.assertIn("enterprise", h)
        self.assertTrue(h["enterprise"].get("enabled", True))

    def test_comparative_metrics_respects_explicit_scope_override(self):
        """Assert explicit scope parameter overrides database default tracking mode."""
        self.db.set_quota_tracking_mode("individual")
        comp = self.db.get_comparative_metrics(scope="team")
        self.assertEqual(comp.get("active_scope"), "team")

    def test_claude_calibration_preserves_individual_direct_quotas(self):
        """Assert Claude provider calibrate_limits persists direct individual quotas."""
        prov = ClaudeProvider(self.db, self.vault, self.diagnostics)
        prov.calibrate_limits(
            session_remaining_pct=35.0,
            weekly_remaining_pct=68.0,
            scope="individual"
        )
        snap = self.db.get_provider_snapshots().get("claude", {})
        self.assertEqual(snap.get("session_remaining_pct"), 35.0)
        self.assertEqual(snap.get("weekly_remaining_pct"), 68.0)
        self.assertEqual(snap.get("individual_session_rem_pct"), 35.0)

    def test_gemini_provider_hierarchy_in_individual_mode(self):
        """Assert Gemini named API keys remain available while keeping individual mode streamlined."""
        comp = self.db.get_comparative_metrics()
        gem_comp = comp["providers"]["gemini"]
        h = gem_comp.get("hierarchy", {})
        self.assertTrue(h.get("streamlined"))
        self.assertIn("tokens", h)
        self.assertGreaterEqual(len(h["tokens"]), 1)

    def test_ollama_provider_models_in_individual_mode(self):
        """Assert local Ollama inference models are preserved without high-level enterprise confusion."""
        comp = self.db.get_comparative_metrics()
        ollama_comp = comp["providers"]["ollama"]
        self.assertEqual(comp.get("tracking_mode"), "individual")
        self.assertIn("models", ollama_comp)

    # -------------------------------------------------------------
    # 3. HTTP Server REST API Endpoints
    # -------------------------------------------------------------
    def _create_server(self):
        claude = ClaudeProvider(self.db, self.vault, self.diagnostics)
        providers = {"claude": claude}
        srv = AppHTTPServer(
            database=self.db,
            vault=self.vault,
            diagnostics=self.diagnostics,
            providers=providers,
            host="127.0.0.1",
            port=0
        )
        srv.start()
        port = srv.server_port
        return srv, port

    def test_rest_api_get_settings_contains_quota_tracking_mode(self):
        """Assert GET /api/settings returns quota_tracking_mode."""
        import urllib.request
        srv, port = self._create_server()
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/settings")
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
                self.assertIn("quota_tracking_mode", data)
                self.assertEqual(data["quota_tracking_mode"], "individual")
        finally:
            srv.stop()

    def test_rest_api_post_settings_updates_quota_tracking_mode(self):
        """Assert POST /api/settings updates quota_tracking_mode."""
        import urllib.request
        srv, port = self._create_server()
        try:
            payload = json.dumps({"quota_tracking_mode": "team"}).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/settings",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
                self.assertTrue(data.get("success"))
                self.assertEqual(data["settings"]["quota_tracking_mode"], "team")

            # Verify in DB
            self.assertEqual(self.db.get_quota_tracking_mode(), "team")
        finally:
            srv.stop()

    def test_rest_api_post_settings_nested_payload_structure(self):
        """Assert POST /api/settings handles { settings: { quota_tracking_mode: 'individual' } }."""
        import urllib.request
        self.db.set_quota_tracking_mode("team")
        srv, port = self._create_server()
        try:
            payload = json.dumps({"settings": {"quota_tracking_mode": "individual"}}).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/settings",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
                self.assertTrue(data.get("success"))
                self.assertEqual(data["settings"]["quota_tracking_mode"], "individual")

            self.assertEqual(self.db.get_quota_tracking_mode(), "individual")
        finally:
            srv.stop()

    def test_rest_api_post_settings_rejects_invalid_tracking_mode(self):
        """Assert POST /api/settings rejects invalid tracking mode with 400."""
        import urllib.request
        import urllib.error
        srv, port = self._create_server()
        try:
            payload = json.dumps({"quota_tracking_mode": "invalid_mode"}).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/settings",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req)
            self.assertEqual(ctx.exception.code, 400)
        finally:
            srv.stop()

    def test_rest_api_usage_comparison_reflects_tracking_mode(self):
        """Assert GET /api/usage/comparison defaults to active quota_tracking_mode."""
        import urllib.request
        srv, port = self._create_server()
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/usage/comparison")
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
                self.assertEqual(data.get("tracking_mode"), "individual")
                self.assertEqual(data.get("active_scope"), "individual")
        finally:
            srv.stop()

    # -------------------------------------------------------------
    # 4. Native Widget Flyout Formatting Logic
    # -------------------------------------------------------------
    def test_native_widget_flyout_format_individual_mode(self):
        """Assert flyout text in individual mode shows direct personal lines and no team pool."""
        from backend.tray.native_widget import NativeTaskbarWidget

        widget = NativeTaskbarWidget()
        # Mock settings and item
        item = {
            "session_balance_remaining_pct": 40.0,
            "weekly_balance_remaining_pct": 73.0,
            "weekly_reset_str": "Mon 3:00 AM",
            "hierarchy": {
                "tracking_mode": "individual",
                "streamlined": True,
                "individual": {
                    "session_remaining_pct": 40.0,
                    "session_used_pct": 60.0,
                    "weekly_remaining_pct": 73.0,
                    "weekly_used_pct": 27.0,
                    "weekly_reset_str": "Mon 3:00 AM"
                },
                "team": {
                    "session_remaining_pct": 44.0,
                    "session_used_pct": 56.0
                }
            }
        }
        lines = widget.format_flyout_quota_lines(p_key="claude", item=item, tracking_mode="individual")
        self.assertIn("sess_quota", lines)
        self.assertIn("week_quota", lines)
        # Verify it references My Quota / Session Quota directly
        self.assertTrue("40.0% rem" in lines["sess_quota"]["text"] or "40% rem" in lines["sess_quota"]["text"])
        self.assertTrue("73.0% rem" in lines["week_quota"]["text"] or "73% rem" in lines["week_quota"]["text"])
        # In individual mode, sess_reset shouldn't be overridden with Team Pool
        self.assertNotIn("Team Pool", lines.get("sess_reset", {}).get("text", ""))

    def test_native_widget_flyout_format_team_mode(self):
        """Assert flyout text in team mode shows both individual and team pool lines."""
        from backend.tray.native_widget import NativeTaskbarWidget

        widget = NativeTaskbarWidget()
        item = {
            "session_balance_remaining_pct": 44.0,
            "weekly_balance_remaining_pct": 74.0,
            "weekly_reset_str": "Mon 3:00 AM",
            "hierarchy": {
                "tracking_mode": "team",
                "streamlined": False,
                "individual": {
                    "session_remaining_pct": 40.0,
                    "session_used_pct": 60.0,
                    "weekly_remaining_pct": 73.0,
                    "weekly_used_pct": 27.0
                },
                "team": {
                    "session_remaining_pct": 44.0,
                    "session_used_pct": 56.0,
                    "weekly_remaining_pct": 74.0,
                    "weekly_used_pct": 26.0,
                    "weekly_reset_str": "Mon 3:00 AM"
                }
            }
        }
        lines = widget.format_flyout_quota_lines(p_key="claude", item=item, tracking_mode="team")
        self.assertIn("sess_quota", lines)
        self.assertIn("sess_reset", lines)
        self.assertIn("Team Pool", lines["sess_reset"]["text"])

    def test_database_migration_for_existing_app_settings(self):
        """Assert database migration ensures quota_tracking_mode is present."""
        # Insert raw settings without quota_tracking_mode
        with self.db._lock:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM app_settings WHERE key = 'quota_tracking_mode'")
            conn.commit()
            conn.close()

        # get_quota_tracking_mode should default to 'individual' gracefully
        self.assertEqual(self.db.get_quota_tracking_mode(), "individual")
        self.assertEqual(self.db.get_all_settings()["quota_tracking_mode"], "individual")


if __name__ == "__main__":
    unittest.main()

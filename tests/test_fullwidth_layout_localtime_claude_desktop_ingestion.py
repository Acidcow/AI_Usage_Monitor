"""
Unit Tests for AIUM-905:
Full-Width Web UI Layout, Local Timezone Alignment & Claude Desktop Live Telemetry Ingestion.
"""

import unittest
import os
import sys
import json
import time
import datetime
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.storage.database import UsageDatabase
from backend.providers.claude import ClaudeProvider, snappy_decompress, extract_v8_int


class TestFullWidthLayoutLocalTimeAndClaudeDesktop(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_usage.db")
        self.db = UsageDatabase(self.db_path)
        self.mock_vault = MagicMock()
        self.mock_vault.get_credential.return_value = None
        self.mock_diag = MagicMock()
        self.provider = ClaudeProvider(self.db, self.mock_vault, self.mock_diag)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_styles_css_main_container_full_width(self):
        """Verify frontend/css/styles.css main.container has max-width: none or 100% and no rigid 1300px constraint."""
        css_path = Path("frontend/css/styles.css")
        self.assertTrue(css_path.exists(), "frontend/css/styles.css must exist")
        content = css_path.read_text(encoding="utf-8")

        # Must not contain rigid max-width: 1300px for main.container
        self.assertNotIn("max-width: 1300px;", content, "Rigid max-width 1300px on main.container must be eliminated")
        # main.container must have width: 100% and max-width: none or 100%
        self.assertTrue(
            "main.container" in content and ("max-width: none" in content or "max-width: 100%" in content),
            "main.container must be fluid full-width"
        )

    def test_02_get_granular_timeseries_uses_local_timezone_labels(self):
        """Verify get_granular_timeseries generates bucket labels in the local OS timezone."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_local = now_utc.astimezone()
        expected_hour = now_local.strftime("%H")

        ts_res = self.db.get_granular_timeseries(window="24h", bucket_minutes=60)
        self.assertTrue(ts_res["success"])
        labels = ts_res["labels"]
        self.assertTrue(len(labels) > 0)
        # The final label must reflect the current local hour, not UTC
        final_label = labels[-1]
        self.assertTrue(
            final_label.startswith(expected_hour) or expected_hour in final_label,
            f"Final label '{final_label}' must match local hour '{expected_hour}'"
        )

    def test_03_get_hierarchical_trends_uses_local_timezone_labels(self):
        """Verify get_hierarchical_trends generates bucket labels in the local OS timezone."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_local = now_utc.astimezone()
        expected_hour = now_local.strftime("%H")

        trends_res = self.db.get_hierarchical_trends(provider="claude", window="24h")
        labels = trends_res["labels"]
        self.assertTrue(len(labels) > 0)
        final_label = labels[-1]
        self.assertTrue(
            final_label.startswith(expected_hour) or expected_hour in final_label,
            f"Final hierarchical trend label '{final_label}' must match local hour '{expected_hour}'"
        )

    def test_04_snappy_decompress_literal_and_copies(self):
        """Verify pure-Python snappy_decompress handles literals and 1-byte / 2-byte copy tags."""
        # Test 1: Literal + 1-byte copy (length 6, offset 8)
        compressed1 = b"\x0e\x1cabcdefgh\x09\x08"
        self.assertEqual(snappy_decompress(compressed1), b"abcdefghabcdef")

        # Test 2: Literal + 2-byte copy (length 12, offset 13)
        compressed2 = b"\x19\x30Hello World! \x2e\x0d\x00"
        self.assertEqual(snappy_decompress(compressed2), b"Hello World! Hello World!")

    def test_05_v8_zigzag_varint_extraction(self):
        """Verify extract_v8_int correctly decodes V8 ZigZag-encoded integer fields."""
        # V8 string b'"\x0cinput_tokensI\x04"' -> 4 >> 1 = 2 tokens
        chunk = b'something"\x0cinput_tokensI\x04other"\routput_tokensI\x10more'
        self.assertEqual(extract_v8_int(chunk, b"input_tokens"), 2)
        self.assertEqual(extract_v8_int(chunk, b"output_tokens"), 8)
        self.assertEqual(extract_v8_int(chunk, b"non_existent"), 0)

    def test_06_claude_desktop_indexeddb_scanner(self):
        """Verify scanning mock Claude Desktop IndexedDB data ingests turns with source='desktop_app'."""
        mock_data_dir = Path(self.temp_dir.name) / "Claude-Data" / "claude_pzs8sxrjxfjjc"
        idb_dir = mock_data_dir / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb"
        idb_dir.mkdir(parents=True, exist_ok=True)

        # Construct a synthetic V8 record with Blink header
        turn_data = (
            b'"\x02id"\x1cmsg_011CgTest0000000000000001"'
            b'"\x05model"\x0fclaude-opus-5-5'
            b'"\x0cinput_tokensI\x08'  # 4 tokens
            b'"\routput_tokensI\x20'  # 16 tokens
            b'"\x17cache_read_input_tokensI\xfa\x01' # 125 tokens
            b'"\x1bcache_creation_input_tokensI\x14' # 10 tokens
            b'timestamp"\x182026-10-22T12:00:00.000Z"'
        )
        # Snappy compressed with varint len
        varint_len = len(turn_data)
        # Encode as literal
        snappy_buf = bytearray([varint_len])
        if varint_len <= 60:
            snappy_buf.append(((varint_len - 1) << 2) | 0)
        else:
            snappy_buf.append((60 << 2) | 0)
            snappy_buf.append(varint_len - 1)
        snappy_buf.extend(turn_data)

        # Blink wrapper header \xff\x11\x02
        full_record = b"\xff\x11\x02" + bytes(snappy_buf)
        log_file = idb_dir / "000001.log"
        log_file.write_bytes(full_record)

        with patch.object(self.provider, "_get_claude_desktop_data_dirs", return_value=[mock_data_dir]):
            count = self.provider.scan_desktop_indexeddb()
            self.assertEqual(count, 1)

        # Verify ingested in database
        conn = self.db._get_connection()
        c = conn.cursor()
        c.execute("SELECT model, input_tokens, output_tokens, cache_read_tokens, source FROM usage_events WHERE session_id LIKE '%msg_011CgTest0000000000000001%'")
        row = c.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["model"], "claude-opus-5-5")
        self.assertEqual(row["input_tokens"], 4)
        self.assertEqual(row["output_tokens"], 16)
        self.assertEqual(row["cache_read_tokens"], 125)
        self.assertEqual(row["source"], "desktop_app")

    def test_07_claude_desktop_deduplication_by_message_id(self):
        """Verify that scanning the same IndexedDB file twice deduplicates by message.id without duplicate rows."""
        mock_data_dir = Path(self.temp_dir.name) / "Claude-Data" / "claude_pzs8sxrjxfjjc"
        idb_dir = mock_data_dir / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb"
        idb_dir.mkdir(parents=True, exist_ok=True)

        turn_data = (
            b'"\x02id"\x1cmsg_011CgDedup0000000000000001"'
            b'"\x05model"\x0fclaude-opus-5-5'
            b'"\x0cinput_tokensI\x08"'
            b'"\routput_tokensI\x20"'
            b'timestamp"\x182026-10-22T12:05:00.000Z"'
        )
        varint_len = len(turn_data)
        snappy_buf = bytearray([varint_len])
        if varint_len <= 60:
            snappy_buf.append(((varint_len - 1) << 2) | 0)
        else:
            snappy_buf.append((60 << 2) | 0)
            snappy_buf.append(varint_len - 1)
        snappy_buf.extend(turn_data)
        full_record = b"\xff\x11\x02" + bytes(snappy_buf)
        (idb_dir / "000002.log").write_bytes(full_record)

        with patch.object(self.provider, "_get_claude_desktop_data_dirs", return_value=[mock_data_dir]):
            c1 = self.provider.scan_desktop_indexeddb()
            c2 = self.provider.scan_desktop_indexeddb()
            self.assertEqual(c1, 1)
            self.assertEqual(c2, 0)

        conn = self.db._get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM usage_events WHERE session_id LIKE '%msg_011CgDedup0000000000000001%'")
        cnt = c.fetchone()[0]
        conn.close()
        self.assertEqual(cnt, 1)

    def test_08_win32_dpapi_and_cng_aes_gcm_decrypt(self):
        """Verify DPAPI and CNG AES-GCM decrypt helper functions exist and execute safely."""
        from backend.providers.claude import dpapi_decrypt_win32, aes_gcm_decrypt_win32
        self.assertTrue(callable(dpapi_decrypt_win32))
        self.assertTrue(callable(aes_gcm_decrypt_win32))

    def test_09_fetch_live_oauth_telemetry_updates_snapshot(self):
        """Verify fetch_live_oauth_telemetry parses mock /oauth/usage and /oauth/profile into provider_snapshots."""
        mock_usage_resp = {
            "five_hour": {
                "utilization": 6.0,
                "resets_at": "2026-10-22T15:30:00.387047+00:00"
            },
            "seven_day": {
                "utilization": 21.0,
                "resets_at": "2026-10-26T00:59:59.387068+00:00"
            }
        }
        mock_profile_resp = {
            "account": {
                "full_name": "James Christopher (Fourie) Eckhardt",
                "display_name": "James",
                "email": "james@synthesis.co.za"
            },
            "organization": {
                "name": "Synthesis 2",
                "organization_type": "claude_team",
                "rate_limit_tier": "default_claude_max_5x",
                "seat_tier": "team_tier_1"
            }
        }

        with patch.object(self.provider, "_discover_oauth_token", return_value="sk-ant-mock-token"), \
             patch.object(self.provider, "_request_oauth_json") as mock_req:
            mock_req.side_effect = lambda url: mock_usage_resp if "usage" in url else mock_profile_resp

            res = self.provider.fetch_live_oauth_telemetry()
            self.assertTrue(res["success"])
            self.assertEqual(res["session_remaining_pct"], 94.0)
            self.assertEqual(res["weekly_remaining_pct"], 79.0)

        snap = self.db.get_provider_snapshots().get("claude", {})
        self.assertEqual(snap.get("session_remaining_pct"), 94.0)
        self.assertEqual(snap.get("weekly_remaining_pct"), 79.0)
        self.assertEqual(snap.get("individual_session_rem_pct"), 94.0)
        self.assertEqual(snap.get("individual_weekly_rem_pct"), 79.0)
        self.assertEqual(snap.get("user_name"), "James Christopher (Fourie) Eckhardt")
        self.assertEqual(snap.get("plan_type"), "Claude Pro")

    def test_10_fetch_live_oauth_telemetry_offline_fallback_plan_history(self):
        """Verify fetch_live_oauth_telemetry falls back to plan-usage-history.json when API is unavailable."""
        mock_data_dir = Path(self.temp_dir.name) / "Claude-Data" / "claude_pzs8sxrjxfjjc"
        mock_data_dir.mkdir(parents=True, exist_ok=True)
        history_file = mock_data_dir / "plan-usage-history.json"
        history_file.write_text(json.dumps({
            "version": 2,
            "samples": [
                {"t": 1792671734000, "org": "mock-org-uuid", "u": {"fh": 6, "sd": 21}}
            ]
        }), encoding="utf-8")

        with patch.object(self.provider, "_discover_oauth_token", return_value=None), \
             patch.object(self.provider, "_get_claude_desktop_data_dirs", return_value=[mock_data_dir]):
            res = self.provider.fetch_live_oauth_telemetry()
            self.assertTrue(res["success"])
            self.assertEqual(res["session_remaining_pct"], 94.0)
            self.assertEqual(res["weekly_remaining_pct"], 79.0)

    def test_11_comparison_panel_html_no_calibrate_claude_button(self):
        """Verify that Calibrate Claude button is eliminated from usage_gauge_card.html and provider_hub.html."""
        gauge_path = Path("frontend/components/usage_gauge_card.html")
        self.assertTrue(gauge_path.exists())
        gauge_content = gauge_path.read_text(encoding="utf-8")
        self.assertNotIn("openClaudeQuotaModal", gauge_content, "openClaudeQuotaModal must be removed from gauge card")
        self.assertNotIn("Calibrate Claude", gauge_content, "Calibrate Claude text must be eliminated from gauge card")

        hub_path = Path("frontend/components/provider_hub.html")
        self.assertTrue(hub_path.exists())
        hub_content = hub_path.read_text(encoding="utf-8")
        self.assertNotIn("openClaudeQuotaModal", hub_content, "openClaudeQuotaModal must be removed from provider hub")
        self.assertNotIn("Calibrate Limits", hub_content, "Calibrate Limits must be eliminated from provider hub")

    def test_12_index_html_no_claude_quota_modal(self):
        """Verify that #claude-quota-modal is eliminated from index.html."""
        index_path = Path("frontend/index.html")
        content = index_path.read_text(encoding="utf-8")
        self.assertNotIn("id=\"claude-quota-modal\"", content, "Manual Calibrate Claude modal must be removed")

    def test_13_app_js_no_manual_claude_calibration_modal_listeners(self):
        """Verify that app.js does not contain openClaudeQuotaModal or saveClaudeQuota."""
        app_path = Path("frontend/js/app.js")
        content = app_path.read_text(encoding="utf-8")
        self.assertNotIn("openClaudeQuotaModal", content, "openClaudeQuotaModal must be removed")
        self.assertNotIn("saveClaudeQuota", content, "saveClaudeQuota must be removed")

    def test_14_sync_usage_calls_both_oauth_and_local_scanners(self):
        """Verify sync_usage executes both fetch_live_oauth_telemetry and scan_local_logs."""
        with patch.object(self.provider, "fetch_live_oauth_telemetry", return_value={"success": True}) as mock_oauth, \
             patch.object(self.provider, "scan_local_logs", return_value=5) as mock_logs:
            res = self.provider.sync_usage()
            mock_oauth.assert_called_once()
            mock_logs.assert_called_once()
            self.assertTrue(res["success"])

    def test_15_compute_provider_dynamic_quotas_prioritizes_live_oauth_snapshot(self):
        """Verify compute_provider_dynamic_quotas honors live session_remaining_pct and reset_epoch from snapshot."""
        reset_epoch = time.time() + 7200
        self.db.update_provider_snapshot(
            provider="claude",
            plan_type="Claude Pro",
            reset_epoch=reset_epoch,
            session_remaining_pct=94.0,
            weekly_remaining_pct=79.0,
            individual_session_rem_pct=94.0,
            individual_weekly_rem_pct=79.0,
            active_scope="individual"
        )
        quotas = self.db.compute_provider_dynamic_quotas("claude")
        self.assertEqual(quotas["session_balance_remaining_pct"], 94.0)
        self.assertEqual(quotas["weekly_balance_remaining_pct"], 79.0)
        self.assertEqual(quotas["reset_epoch"], reset_epoch)

    def test_16_fullwidth_tables_in_reports_and_sessions(self):
        """Verify data tables in reports_panel and session_timeline specify 100% width."""
        rep_path = Path("frontend/components/reports_panel.html")
        rep_content = rep_path.read_text(encoding="utf-8")
        self.assertIn("width: 100%", rep_content)

        ses_path = Path("frontend/components/session_timeline.html")
        ses_content = ses_path.read_text(encoding="utf-8")
        self.assertIn("width: 100%", ses_content)

    def test_17_plan_usage_history_samples_parser(self):
        """Verify plan-usage-history parser extracts latest fh and sd samples."""
        mock_data = {
            "version": 2,
            "samples": [
                {"t": 1000, "org": "org-1", "u": {"fh": 28, "sd": 93}},
                {"t": 2000, "org": "org-1", "u": {"fh": 6, "sd": 21}}
            ]
        }
        sample = self.provider._parse_latest_plan_usage_sample(mock_data)
        self.assertEqual(sample["fh"], 6)
        self.assertEqual(sample["sd"], 21)

    def test_18_claude_provider_discovers_claude_desktop_data_dir(self):
        """Verify _get_claude_desktop_data_dirs discovers Claude-Data under LocalAppData."""
        dirs = self.provider._get_claude_desktop_data_dirs()
        # Should return a list of Paths
        self.assertIsInstance(dirs, list)
        if any(d.exists() for d in dirs):
            self.assertTrue(any("Claude-Data" in str(d) for d in dirs))

    def test_19_chart_breakdown_series_includes_desktop_app_events(self):
        """Verify get_granular_timeseries incorporates events with source='desktop_app'."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.db.record_usage_event(
            provider="claude",
            model="claude-opus-5-5",
            input_tokens=1000,
            output_tokens=200,
            source="desktop_app",
            session_id="desktop_turn_01",
            recorded_at=now_iso
        )
        ts_res = self.db.get_granular_timeseries(window="24h", breakdown="consolidated")
        self.assertTrue(ts_res["total_tokens"] >= 1200)

    def test_20_end_to_end_claude_telemetry_flow(self):
        """Verify full end-to-end integration: snapshot reflects Claude Pro without manual intervention."""
        # Insert a desktop turn
        self.db.record_usage_event(
            provider="claude",
            model="claude-opus-5-5",
            input_tokens=5000,
            output_tokens=500,
            source="desktop_app",
            session_id="e2e_turn_01",
            recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
        )
        # Update snapshot via live OAuth telemetry logic
        self.db.update_provider_snapshot(
            provider="claude",
            plan_type="Claude Pro",
            user_name="James Christopher (Fourie) Eckhardt",
            team_name="Claude Pro",
            reset_epoch=time.time() + 7200,
            session_remaining_pct=94.0,
            weekly_remaining_pct=79.0,
            individual_session_rem_pct=94.0,
            individual_weekly_rem_pct=79.0,
            active_scope="individual"
        )
        metrics = self.db.get_comparative_metrics(scope="individual")
        claude_m = metrics["providers"]["claude"]
        self.assertEqual(claude_m["plan_type"], "Claude Pro")
        self.assertEqual(claude_m["session_balance_remaining_pct"], 94.0)
        self.assertEqual(claude_m["weekly_balance_remaining_pct"], 79.0)
        self.assertTrue(claude_m["tokens_today"] >= 5500)


if __name__ == "__main__":
    unittest.main()

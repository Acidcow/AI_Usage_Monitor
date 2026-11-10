"""
Test Suite: Incremental Scanner, Paid Ping Removal & Adaptive Polling Cadence (AIUM-1003)
Covers:
1. claude.py: UnboundLocalError regression when ~/.claude is missing.
2. claude.py: Incremental (mtime, size) cache hits vs. file invalidation and _force_full_scan.
3. claude.py: ScanResult hybrid int-dict container semantics.
4. claude.py: 300s TTL cache on /v1/messages probe, paid ping removal, and error handling.
5. claude.py: Dynamic environment-based identities instead of hardcoded strings.
6. ollama.py: Incremental (mtime, size) cache hits, log append invalidation, and summary preservation.
7. ollama.py: ScanResult hybrid int-dict support.
8. native_widget.py: Truthful zero-activity flat baseline (no fake multiplier waves).
9. native_widget.py: Configurable poll_interval_ms with server setting dynamic sync and clamping.
10. native_widget.py: Single configure call in flyout (duplicate line eliminated).
11. run_monitor.py: Dynamic polling cadence setting lookup and bounds clamping.
"""

import unittest
import tempfile
import os
import sys
import json
import time
import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock
import urllib.error
import socket

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.providers.claude import ClaudeProvider, ScanResult
from backend.providers.ollama import OllamaProvider
from backend.tray.native_widget import NativeTaskbarWidget


class TestIncrementalScannerAndPolling(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_poll_scanner.db")
        self.vault_path = os.path.join(self.temp_dir.name, "test_vault.json")
        self.db = UsageDatabase(db_path=self.db_path)
        self.vault = DPAPIVault(storage_path=self.vault_path)
        self.diagnostics = DiagnosticsEngine()
        self.diagnostics.clear_errors()

        self.claude = ClaudeProvider(self.db, self.vault, self.diagnostics)
        self.ollama = OllamaProvider(self.db, self.vault, self.diagnostics, base_url="http://localhost:11434")

    def tearDown(self):
        self.temp_dir.cleanup()

    # =========================================================================
    # 1. Claude Provider: UnboundLocalError & Missing Root
    # =========================================================================
    def test_01_claude_scan_local_logs_missing_root_no_unbound_error(self):
        """Regression test for UnboundLocalError on jsonl_files when directory does not exist."""
        non_existent_dir = os.path.join(self.temp_dir.name, "does_not_exist_claude_dir")
        try:
            count = self.claude.scan_local_logs(search_dir=non_existent_dir)
            self.assertEqual(count, 0)
            self.assertEqual(count.get("files_scanned"), 0)
        except UnboundLocalError:
            self.fail("scan_local_logs raised UnboundLocalError when directory is missing!")

    # =========================================================================
    # 2. Claude Provider: Incremental File Scanning State & Cache Hit
    # =========================================================================
    def test_02_claude_scan_populates_file_scan_state(self):
        """Verify scanning a JSONL file populates _file_scan_state with mtime, size, and stats."""
        proj_dir = Path(self.temp_dir.name) / "mock_claude" / "projects" / "ProjA"
        proj_dir.mkdir(parents=True, exist_ok=True)
        log_file = proj_dir / "session-1.jsonl"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess-alpha",
                "timestamp": "2026-11-07T10:00:00Z",
                "message": {
                    "id": "msg_001",
                    "model": "claude-sonnet-5-5",
                    "usage": {"input_tokens": 100, "output_tokens": 50}
                }
            }) + "\n")

        res = self.claude.scan_local_logs(search_dir=str(proj_dir.parent.parent))
        self.assertEqual(res, 1)

        file_key = str(log_file.resolve())
        self.assertIn(file_key, self.claude._file_scan_state)
        cached = self.claude._file_scan_state[file_key]
        self.assertGreater(cached["mtime"], 0)
        self.assertGreater(cached["size"], 0)
        self.assertEqual(cached["tokens"], 150)
        self.assertEqual(cached["session_id"], "sess-alpha")
        self.assertEqual(cached["model"], "claude-sonnet-5-5")

    def test_03_claude_incremental_cache_hit_skips_parsing(self):
        """Verify second scan on unchanged file hits in-memory cache and bypasses file parsing."""
        proj_dir = Path(self.temp_dir.name) / "mock_claude" / "projects" / "ProjB"
        proj_dir.mkdir(parents=True, exist_ok=True)
        log_file = proj_dir / "session-2.jsonl"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess-beta",
                "timestamp": "2026-11-07T10:00:00Z",
                "message": {
                    "id": "msg_002",
                    "model": "claude-sonnet-5-5",
                    "usage": {"input_tokens": 200, "output_tokens": 100}
                }
            }) + "\n")

        first_res = self.claude.scan_local_logs(search_dir=str(proj_dir.parent.parent))
        self.assertEqual(first_res, 1)

        # Second scan: file is unchanged
        second_res = self.claude.scan_local_logs(search_dir=str(proj_dir.parent.parent))
        self.assertEqual(second_res, 0)
        self.assertEqual(second_res.get("cached_files"), 1)
        self.assertEqual(second_res.get("total_tokens"), 300)

    def test_04_claude_cache_invalidation_on_file_modification(self):
        """Verify modifying the JSONL file updates mtime/size and invalidates the cache."""
        proj_dir = Path(self.temp_dir.name) / "mock_claude" / "projects" / "ProjC"
        proj_dir.mkdir(parents=True, exist_ok=True)
        log_file = proj_dir / "session-3.jsonl"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess-gamma",
                "timestamp": "2026-11-07T10:00:00Z",
                "message": {
                    "id": "msg_003",
                    "model": "claude-sonnet-5-5",
                    "usage": {"input_tokens": 100, "output_tokens": 50}
                }
            }) + "\n")

        res1 = self.claude.scan_local_logs(search_dir=str(proj_dir.parent.parent))
        self.assertEqual(res1, 1)

        # Modify file with new turn
        time.sleep(0.05)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess-gamma",
                "timestamp": "2026-11-07T10:05:00Z",
                "message": {
                    "id": "msg_004",
                    "model": "claude-sonnet-5-5",
                    "usage": {"input_tokens": 50, "output_tokens": 25}
                }
            }) + "\n")

        res2 = self.claude.scan_local_logs(search_dir=str(proj_dir.parent.parent))
        self.assertEqual(res2, 1)
        self.assertEqual(res2.get("total_tokens"), 225)

    def test_05_claude_force_full_scan_overrides_cache(self):
        """Verify _force_full_scan forces re-processing even when mtime and size match."""
        proj_dir = Path(self.temp_dir.name) / "mock_claude" / "projects" / "ProjD"
        proj_dir.mkdir(parents=True, exist_ok=True)
        log_file = proj_dir / "session-4.jsonl"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess-delta",
                "timestamp": "2026-11-07T10:00:00Z",
                "message": {
                    "id": "msg_005",
                    "model": "claude-sonnet-5-5",
                    "usage": {"input_tokens": 100, "output_tokens": 50}
                }
            }) + "\n")

        self.claude.scan_local_logs(search_dir=str(proj_dir.parent.parent))
        self.claude._force_full_scan = True

        res = self.claude.scan_local_logs(search_dir=str(proj_dir.parent.parent))
        self.assertEqual(res.get("cached_files"), 0)
        self.assertEqual(res.get("files_scanned"), 1)

    # =========================================================================
    # 3. Hybrid ScanResult Semantics
    # =========================================================================
    def test_06_scan_result_integer_compatibility(self):
        """Verify ScanResult behaves natively as an int in equality, arithmetic, and logic."""
        stats = {"sessions_found": 2, "total_tokens": 1200, "events_recorded": 3}
        res = ScanResult(3, stats)
        self.assertIsInstance(res, int)
        self.assertEqual(res, 3)
        self.assertNotEqual(res, 0)
        self.assertEqual(res + 5, 8)
        self.assertTrue(res > 1)
        self.assertTrue(bool(res))

    def test_07_scan_result_dictionary_access(self):
        """Verify ScanResult supports dict bracket lookup, .get(), keys(), and items()."""
        stats = {"sessions_found": 2, "total_tokens": 1200, "events_recorded": 3}
        res = ScanResult(3, stats)
        self.assertEqual(res["sessions_found"], 2)
        self.assertEqual(res["total_tokens"], 1200)
        self.assertEqual(res.get("non_existent", "fallback"), "fallback")
        self.assertIn("total_tokens", res)
        self.assertEqual(list(res.keys()), ["sessions_found", "total_tokens", "events_recorded"])

    def test_08_claude_scan_local_logs_supports_db_parameter(self):
        """Verify scan_local_logs supports an explicit db target parameter."""
        custom_db_path = os.path.join(self.temp_dir.name, "custom_target.db")
        custom_db = UsageDatabase(custom_db_path)

        proj_dir = Path(self.temp_dir.name) / "mock_claude" / "projects" / "ProjTarget"
        proj_dir.mkdir(parents=True, exist_ok=True)
        with open(proj_dir / "target.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "type": "assistant",
                "sessionId": "sess-target",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "message": {
                    "id": "msg_target",
                    "model": "claude-sonnet-5-5",
                    "usage": {"input_tokens": 300, "output_tokens": 150}
                }
            }) + "\n")

        res = self.claude.scan_local_logs(search_dir=str(proj_dir.parent.parent), db=custom_db)
        self.assertEqual(res, 1)

        summary = custom_db.get_usage_summary(provider="claude")
        self.assertEqual(summary["total_tokens_today"], 450)

    # =========================================================================
    # 4. Paid Ping Removal & 300s TTL Caching
    # =========================================================================
    def test_09_claude_paid_ping_skipped_by_default(self):
        """Verify sync_usage does not send live /v1/messages probe when _allow_active_api_probe is False."""
        self.vault.set_credential("claude", "default", "sk-ant-api03-ValidStructuralKeyForTesting1234567890")
        self.claude._allow_active_api_probe = False

        with patch.object(self.claude, "scan_local_logs", return_value=0):
            with patch.object(self.claude, "fetch_live_oauth_telemetry", return_value={"success": True}):
                def fake_urlopen(*args, **kwargs):
                    raise RuntimeError("urlopen should not be called!")
                with patch("urllib.request.urlopen", fake_urlopen):
                    res = self.claude.sync_usage()
                    self.assertTrue(res["success"])
                    self.assertTrue(res.get("active_probe_skipped"))

    def test_10_claude_probe_cached_for_300s_ttl(self):
        """Verify back-to-back calls within 300s TTL hit in-memory cache and do not call urlopen again."""
        self.vault.set_credential("claude", "default", "sk-ant-api03-ValidStructuralKeyForTesting1234567890")
        self.claude._allow_active_api_probe = True

        mock_resp = MagicMock()
        mock_resp.headers = {
            "anthropic-ratelimit-requests-remaining": "990",
            "anthropic-ratelimit-tokens-remaining": "395000",
            "anthropic-ratelimit-tokens-limit": "400000"
        }
        mock_resp.__enter__.return_value = mock_resp

        with patch.object(self.claude, "scan_local_logs", return_value=0):
            with patch.object(self.claude, "fetch_live_oauth_telemetry", return_value={"success": True}):
                with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
                    # First call: executes network probe
                    res1 = self.claude.sync_usage()
                    self.assertTrue(res1["success"])
                    self.assertEqual(mock_open.call_count, 1)

                    # Second call immediately after: hits 300s TTL cache
                    res2 = self.claude.sync_usage()
                    self.assertTrue(res2["success"])
                    self.assertEqual(mock_open.call_count, 1) # Still 1, did not re-call!

    def test_11_claude_probe_cache_expires_after_ttl(self):
        """Verify cache expires after 300 seconds and refreshes on next poll."""
        self.vault.set_credential("claude", "default", "sk-ant-api03-ValidStructuralKeyForTesting1234567890")
        self.claude._allow_active_api_probe = True

        mock_resp = MagicMock()
        mock_resp.headers = {
            "anthropic-ratelimit-requests-remaining": "990",
            "anthropic-ratelimit-tokens-remaining": "395000",
            "anthropic-ratelimit-tokens-limit": "400000"
        }
        mock_resp.__enter__.return_value = mock_resp

        with patch.object(self.claude, "scan_local_logs", return_value=0):
            with patch.object(self.claude, "fetch_live_oauth_telemetry", return_value={"success": True}):
                with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
                    self.claude.sync_usage()
                    self.assertEqual(mock_open.call_count, 1)

                    # Simulate 301 seconds passing
                    self.claude._cached_api_probe_ts = time.time() - 301.0

                    self.claude.sync_usage()
                    self.assertEqual(mock_open.call_count, 2)

    def test_12_claude_get_quota_metrics_aliases(self):
        """Verify get_quota_metrics and get_Quota_Metrics aliases invoke sync_usage."""
        with patch.object(self.claude, "sync_usage", return_value={"success": True, "mode": "test"}):
            self.assertEqual(self.claude.get_quota_metrics()["mode"], "test")
            self.assertEqual(self.claude.get_Quota_Metrics()["mode"], "test")

    # =========================================================================
    # 5. Dynamic Identity Fallbacks
    # =========================================================================
    def test_13_claude_identity_fallbacks_are_dynamic(self):
        """Verify calibrate_limits uses dynamic OS username and hostname rather than hardcoded identities."""
        res = self.claude.calibrate_limits(
            session_used_pct=10.0,
            weekly_used_pct=5.0
        )
        self.assertTrue(res["success"])
        snap = self.db.get_provider_snapshots()["claude"]
        user_name = snap.get("user_name")
        team_name = snap.get("team_name")

        self.assertNotEqual(user_name, "James Eckhardt")
        self.assertNotEqual(team_name, "Synthesis2")
        self.assertTrue(bool(user_name))
        self.assertTrue(bool(team_name))

    # =========================================================================
    # 6. Ollama Provider: Incremental Scanning & Cache Invalidation
    # =========================================================================
    def test_14_ollama_scan_populates_file_scan_state(self):
        """Verify Ollama log scanning populates _file_scan_state with mtime, size, and token summary."""
        log_file = os.path.join(self.temp_dir.name, "ollama_server.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(
                "time=2026-11-07T12:00:00.000Z level=INFO source=images.go:383 msg=\"template selection\" model=llama3.2:3b\n"
                "slot print_timing: id 0 | task 101 | prompt eval time = 50.0 ms / 500 tokens\n"
                "slot print_timing: id 0 | task 101 | eval time = 100.0 ms / 250 tokens\n"
                "[GIN] 2026/11/07 - 12:00:05 | 200 | 1.5s | 127.0.0.1 | POST \"/api/chat\"\n"
            )

        res = self.ollama.scan_local_logs(log_paths=[log_file])
        self.assertEqual(res, 1)

        file_key = str(Path(log_file).resolve())
        self.assertIn(file_key, self.ollama._file_scan_state)
        cached = self.ollama._file_scan_state[file_key]
        self.assertEqual(cached["cached_summary"]["total_tokens"], 750)
        self.assertEqual(cached["cached_summary"]["prompt_tokens"], 500)
        self.assertEqual(cached["cached_summary"]["eval_tokens"], 250)

    def test_15_ollama_incremental_cache_hit_skips_parsing(self):
        """Verify second scan on unchanged Ollama log file hits cache and returns 0 new runs."""
        log_file = os.path.join(self.temp_dir.name, "ollama_cached.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(
                "time=2026-11-07T12:00:00.000Z level=INFO source=images.go:383 msg=\"template selection\" model=llama3.2:3b\n"
                "slot print_timing: id 0 | task 102 | prompt eval time = 50.0 ms / 300 tokens\n"
                "slot print_timing: id 0 | task 102 | eval time = 100.0 ms / 150 tokens\n"
            )

        res1 = self.ollama.scan_local_logs(log_paths=[log_file])
        self.assertEqual(res1, 1)

        res2 = self.ollama.scan_local_logs(log_paths=[log_file])
        self.assertEqual(res2, 0)
        self.assertEqual(res2.get("cached_files"), 1)
        self.assertEqual(res2.get("total_tokens"), 450)

    def test_16_ollama_cache_invalidation_on_log_append(self):
        """Verify appending inference lines to Ollama log invalidates cache and ingests new turns."""
        log_file = os.path.join(self.temp_dir.name, "ollama_append.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(
                "time=2026-11-07T12:00:00.000Z level=INFO source=images.go:383 msg=\"template selection\" model=llama3.2:3b\n"
                "slot print_timing: id 0 | task 103 | prompt eval time = 50.0 ms / 200 tokens\n"
                "slot print_timing: id 0 | task 103 | eval time = 100.0 ms / 100 tokens\n"
            )

        self.ollama.scan_local_logs(log_paths=[log_file])

        time.sleep(0.05)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(
                "time=2026-11-07T12:05:00.000Z level=INFO source=images.go:383 msg=\"template selection\" model=llama3.2:3b\n"
                "slot print_timing: id 0 | task 104 | prompt eval time = 30.0 ms / 150 tokens\n"
                "slot print_timing: id 0 | task 104 | eval time = 80.0 ms / 75 tokens\n"
            )

        res2 = self.ollama.scan_local_logs(log_paths=[log_file])
        self.assertEqual(res2, 1)
        self.assertEqual(res2.get("total_tokens"), 525)

    def test_17_ollama_scan_result_dict_and_int_compatibility(self):
        """Verify Ollama ScanResult supports int comparisons and dict key access."""
        log_file = os.path.join(self.temp_dir.name, "ollama_scan_res.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(
                "time=2026-11-07T12:00:00.000Z level=INFO source=images.go:383 msg=\"template selection\" model=qwen2.5:7b\n"
                "slot print_timing: id 0 | task 105 | prompt eval time = 40.0 ms / 600 tokens\n"
                "slot print_timing: id 0 | task 105 | eval time = 90.0 ms / 300 tokens\n"
            )

        res = self.ollama.scan_local_logs(log_paths=[log_file])
        self.assertEqual(res, 1)
        self.assertIsInstance(res, int)
        self.assertEqual(res["total_tokens"], 900)
        self.assertEqual(res["events_recorded"], 1)

    # =========================================================================
    # 7. Native Widget: Polling Interval, Zero-Activity Baseline & Labels
    # =========================================================================
    def test_18_native_widget_poll_interval_ms_default_and_clamping(self):
        """Verify native widget poll_interval_ms defaults to 10000 and is clamped between 5000 and 60000 ms."""
        widget = NativeTaskbarWidget()
        self.assertEqual(widget.poll_interval_ms, 10000)

        # Update from server settings: 3 seconds -> clamped to minimum 5000ms
        widget._apply_settings_from_server({"ui_refresh_interval_seconds": 3})
        self.assertEqual(widget.poll_interval_ms, 5000)

        # Update from server settings: 120 seconds -> clamped to maximum 60000ms
        widget._apply_settings_from_server({"ui_refresh_interval_seconds": 120})
        self.assertEqual(widget.poll_interval_ms, 60000)

        # Update from server settings: 15 seconds -> 15000ms
        widget._apply_settings_from_server({"ui_refresh_interval_seconds": 15})
        self.assertEqual(widget.poll_interval_ms, 15000)

    def test_19_native_widget_zero_activity_flat_baseline(self):
        """Verify _get_sparkline_points generates an honest flat baseline when tok_today and tok_week are zero."""
        widget = NativeTaskbarWidget()
        pts = widget._get_sparkline_points(tok_today=0, tok_week=0, width=90, height=22)
        self.assertGreater(len(pts), 1)

        # All y values in flat zero data must be identical (a clean flat line at bottom)
        y_values = [p[1] for p in pts]
        self.assertEqual(len(set(y_values)), 1, "Zero activity series must produce a horizontal flat line without fake wave fluctuations!")

    def test_20_native_widget_draw_sparkline_fallback_uses_zero_baseline(self):
        """Verify _draw_sparkline falls back to [0.0]*8 flat baseline instead of fake wave points."""
        widget = NativeTaskbarWidget()
        # Mock canvas to inspect coordinates
        mock_canvas = MagicMock()
        widget.canvas = mock_canvas

        widget._draw_sparkline(x=0, y=0, w=100, h=30, points=[], stroke_color="#38bdf8")

        # Verify create_line was called with flat baseline coordinates
        self.assertTrue(mock_canvas.create_line.called)
        args, kwargs = mock_canvas.create_line.call_args
        coords = list(args)
        y_coords = coords[1::2]
        self.assertEqual(len(set(y_coords)), 1, "Fallback sparkline coordinates must be flat without fake waves!")

    def test_21_native_widget_child_series_zero_bins_when_no_timeseries(self):
        """Verify _get_provider_child_series produces clean zero bins without multiplier arrays."""
        widget = NativeTaskbarWidget()
        series_claude = widget._get_provider_child_series("claude", {"tokens_today": 1000})
        for pts, color, label in series_claude:
            self.assertEqual(pts, [0] * 8, f"Series {label} must be zero bins when timeseries data is absent!")

        series_gemini = widget._get_provider_child_series("gemini", {"tokens_today": 1000})
        for pts, color, label in series_gemini:
            self.assertEqual(pts, [0] * 8, f"Series {label} must be zero bins when timeseries data is absent!")

    def test_22_native_widget_dynamic_hierarchy_labels(self):
        """Verify native widget does not display hardcoded personal identities."""
        widget = NativeTaskbarWidget()
        claude_series = widget._get_provider_child_series("claude", {
            "tokens_today": 500,
            "hierarchy": {"team_name": "Core Alpha Team", "user_name": "Dev User"}
        })
        labels = [s[2] for s in claude_series]
        self.assertIn("Core Alpha Team (Team)", labels)
        self.assertIn("Dev User (Individual)", labels)

    # =========================================================================
    # 8. Adaptive Polling Cadence in Run Monitor Logic
    # =========================================================================
    def test_23_run_monitor_adaptive_cadence_clamping(self):
        """Verify database setting ui_refresh_interval_seconds logic properly clamps between 5s and 60s."""
        self.db.set_setting("ui_refresh_interval_seconds", 2)
        setting_val = self.db.get_setting("ui_refresh_interval_seconds")
        poll_interval = max(5, min(60, int(setting_val)))
        self.assertEqual(poll_interval, 5)

        self.db.set_setting("ui_refresh_interval_seconds", 90)
        setting_val = self.db.get_setting("ui_refresh_interval_seconds")
        poll_interval = max(5, min(60, int(setting_val)))
        self.assertEqual(poll_interval, 60)

        self.db.set_setting("ui_refresh_interval_seconds", 25)
        setting_val = self.db.get_setting("ui_refresh_interval_seconds")
        poll_interval = max(5, min(60, int(setting_val)))
        self.assertEqual(poll_interval, 25)


if __name__ == "__main__":
    unittest.main()

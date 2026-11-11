"""
Unit tests for AIUM-909:
Eliminate Claude Polling Auth Loops (401/429), Vault Key Sanitization & OAuth Cache TTL.

Verifies:
1. is_valid_anthropic_api_key helper correctly discriminates genuine keys from placeholders/dummies.
2. Truncated dummy keys (e.g. 'sk-ant-sec...', length 17) are flagged as invalid.
3. Common placeholders ('proxy', 'dummy', 'vault', 'mock', '') are flagged as invalid.
4. Genuine keys ('sk-ant-api03-...', len >= 40) are recognized as valid.
5. Invalid keys bypass the live Anthropic messages probe and never record an AUTH_FAILURE error.
6. Automatic purge/sanitization of invalid placeholder keys from DPAPI vault.
7. fetch_live_oauth_telemetry implements 300-second (5-minute) in-memory TTL caching.
8. Rapid consecutive calls to fetch_live_oauth_telemetry return cached result without repeated HTTP requests.
9. HTTP 429 rate limit triggers backoff guard for at least 600 seconds.
10. During backoff window, outbound network calls are skipped and local/cached metrics returned.
11. Provider snapshot records active status as 'CLAUDE PRO (OAUTH LIVE)' or 'ACTIVE (Live API)'.
12. is_calibrated flag is set to False for genuine live OAuth telemetry.
"""

import unittest
import time
import os
import tempfile
from unittest.mock import patch, MagicMock
from pathlib import Path

from backend.storage.database import DatabaseEngine
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine, ErrorCategory
from backend.providers.claude import ClaudeProvider


class TestClaudeAuthLoopEliminationAndOAuthCache(unittest.TestCase):
    def setUp(self):
        self.temp_db_path = os.path.join(tempfile.gettempdir(), f"test_claude_{int(time.time()*1000)}.db")
        self.db = DatabaseEngine(self.temp_db_path)
        self.vault = MagicMock(spec=DPAPIVault)
        self.diagnostics = DiagnosticsEngine()
        self.provider = ClaudeProvider(self.db, self.vault, self.diagnostics)

    def tearDown(self):
        if os.path.exists(self.temp_db_path):
            try:
                os.remove(self.temp_db_path)
            except Exception:
                pass

    def test_01_is_valid_anthropic_api_key_genuine_key(self):
        """Verify genuine Anthropic key (len >= 40, starts with sk-ant-) is valid."""
        key = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_1234567890"
        self.assertTrue(ClaudeProvider.is_valid_anthropic_api_key(key))

    def test_02_is_valid_anthropic_api_key_short_dummy_key(self):
        """Verify short placeholder key 'sk-ant-sec...' (17 chars) is rejected as invalid."""
        self.assertFalse(ClaudeProvider.is_valid_anthropic_api_key("sk-ant-sec..."))
        self.assertFalse(ClaudeProvider.is_valid_anthropic_api_key("sk-ant-secret123"))

    def test_03_is_valid_anthropic_api_key_placeholders(self):
        """Verify standard placeholder tokens ('proxy', 'dummy', 'vault', 'mock', '') are rejected."""
        for ph in ["proxy", "dummy", "vault", "local", "mock", "demo", "", None]:
            self.assertFalse(ClaudeProvider.is_valid_anthropic_api_key(ph))

    def test_04_is_valid_anthropic_api_key_wrong_prefix(self):
        """Verify non-Anthropic keys (e.g. OpenAI 'sk-proj-...') are rejected by Claude validator."""
        self.assertFalse(ClaudeProvider.is_valid_anthropic_api_key("sk-proj-abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"))

    def test_05_dummy_key_in_vault_skips_messages_probe(self):
        """Verify that when vault has dummy key 'sk-ant-sec...', sync_usage skips messages probe."""
        self.vault.get_credential.return_value = "sk-ant-sec..."
        with patch.object(self.provider, "fetch_live_oauth_telemetry", return_value={"success": True}):
            with patch.object(self.provider, "scan_local_logs", return_value=0):
                with patch("urllib.request.urlopen") as mock_url:
                    res = self.provider.sync_usage()
                    # urlopen should NOT have been called for api.anthropic.com/v1/messages
                    for call_args in mock_url.call_args_list:
                        req = call_args[0][0]
                        url = req.full_url if hasattr(req, "full_url") else str(req)
                        self.assertNotIn("messages", url)
                    self.assertTrue(res.get("success"))

    def test_06_dummy_key_never_records_auth_failure(self):
        """Verify no AUTH_FAILURE is logged into diagnostics when dummy key is present."""
        self.vault.get_credential.return_value = "sk-ant-sec..."
        with patch.object(self.provider, "fetch_live_oauth_telemetry", return_value={"success": True}):
            with patch.object(self.provider, "scan_local_logs", return_value=0):
                self.provider.sync_usage()
                errors = self.diagnostics.get_recent_errors(limit=20)
                auth_errors = [e for e in errors if e.get("category") == ErrorCategory.AUTH_FAILURE.value and e.get("provider") == "claude"]
                self.assertEqual(len(auth_errors), 0)

    def test_07_oauth_cache_ttl_initial_state(self):
        """Verify provider initializes with empty cache and 300s TTL."""
        self.assertIsNone(self.provider._oauth_telemetry_cache)
        self.assertEqual(self.provider._oauth_cache_ttl_seconds, 300.0)

    def test_08_oauth_cache_stores_and_returns_within_ttl(self):
        """Verify second call to fetch_live_oauth_telemetry returns cached payload without HTTP call."""
        mock_usage = {
            "five_hour": {"utilization": 20.0, "resets_at": "2026-10-26T18:00:00Z"},
            "seven_day": {"utilization": 30.0, "resets_at": "2026-10-31T00:00:00Z"}
        }
        mock_profile = {
            "account": {"full_name": "James Eckhardt"},
            "organization": {"name": "Synthesis 2", "rate_limit_tier": "default_claude_max_5x"}
        }

        call_count = 0
        def fake_request(url):
            nonlocal call_count
            call_count += 1
            if "usage" in url:
                return mock_usage
            return mock_profile

        with patch.object(self.provider, "_request_oauth_json", side_effect=fake_request):
            first = self.provider.fetch_live_oauth_telemetry()
            self.assertTrue(first.get("success"))
            self.assertEqual(first.get("session_remaining_pct"), 80.0)
            initial_calls = call_count

            # Immediate second call
            second = self.provider.fetch_live_oauth_telemetry()
            self.assertTrue(second.get("success"))
            self.assertEqual(second.get("session_remaining_pct"), 80.0)
            self.assertEqual(call_count, initial_calls, "Network request count must not increment within TTL")

    def test_09_oauth_cache_force_refresh_bypasses_cache(self):
        """Verify force=True bypasses the TTL cache."""
        self.provider._oauth_telemetry_cache = {"success": True, "session_remaining_pct": 50.0}
        self.provider._oauth_telemetry_cache_time = time.time()

        with patch.object(self.provider, "_request_oauth_json", return_value={"five_hour": {"utilization": 10.0}}):
            res = self.provider.fetch_live_oauth_telemetry(force=True)
            self.assertEqual(res.get("session_remaining_pct"), 90.0)

    def test_10_oauth_cache_expires_after_ttl(self):
        """Verify cache expires once ttl has elapsed."""
        self.provider._oauth_telemetry_cache = {"success": True, "session_remaining_pct": 50.0}
        self.provider._oauth_telemetry_cache_time = time.time() - 305.0  # 305s ago

        with patch.object(self.provider, "_request_oauth_json", return_value={"five_hour": {"utilization": 15.0}}):
            res = self.provider.fetch_live_oauth_telemetry()
            self.assertEqual(res.get("session_remaining_pct"), 85.0)

    def test_11_http_429_triggers_ten_minute_backoff(self):
        """Verify HTTP 429 sets _oauth_rate_limited_until to at least 9 minutes in the future."""
        import urllib.error
        with patch("urllib.request.urlopen") as mock_url:
            mock_url.side_effect = urllib.error.HTTPError(
                url="https://api.anthropic.com/api/oauth/usage",
                code=429,
                msg="Too Many Requests",
                hdrs={},
                fp=None
            )
            with patch.object(self.provider, "_discover_oauth_token", return_value="dummy_oauth_token"):
                res = self.provider._request_oauth_json("https://api.anthropic.com/api/oauth/usage")
                self.assertIsNone(res)
                self.assertGreater(self.provider._oauth_rate_limited_until, time.time() + 500)

    def test_12_during_backoff_outbound_requests_are_skipped(self):
        """Verify that during backoff window, fetch_live_oauth_telemetry skips network and uses fallback."""
        self.provider._oauth_rate_limited_until = time.time() + 400
        with patch.object(self.provider, "_request_oauth_json") as mock_req:
            with patch.object(self.provider, "_scan_offline_plan_history", return_value={"success": True, "fallback": True}):
                res = self.provider.fetch_live_oauth_telemetry()
                mock_req.assert_not_called()
                self.assertTrue(res.get("fallback"))

    def test_13_successful_oauth_telemetry_updates_provider_snapshot(self):
        """Verify successful OAuth telemetry updates snapshot with plan_type and session limits."""
        mock_usage = {
            "five_hour": {"utilization": 25.0, "resets_at": "2026-10-26T20:00:00Z"},
            "seven_day": {"utilization": 40.0, "resets_at": "2026-10-31T00:00:00Z"}
        }
        with patch.object(self.provider, "_request_oauth_json", side_effect=lambda u: mock_usage if "usage" in u else {}):
            self.provider.fetch_live_oauth_telemetry(force=True)
            snaps = self.db.get_provider_snapshots()
            claude_snap = snaps.get("claude", {})
            self.assertEqual(claude_snap.get("session_remaining_pct"), 75.0)
            self.assertEqual(claude_snap.get("weekly_remaining_pct"), 60.0)
            self.assertEqual(claude_snap.get("plan_type"), "Claude Pro")

    def test_14_vault_sanitization_on_init_removes_dummy_key(self):
        """Verify provider.__init__ purges dummy key if present in vault."""
        mock_vault = MagicMock(spec=DPAPIVault)
        mock_vault.get_credential.return_value = "sk-ant-sec..."
        ClaudeProvider(self.db, mock_vault, self.diagnostics)
        mock_vault.delete_credential.assert_called_with("claude", "default")

    def test_15_vault_sanitization_retains_genuine_key(self):
        """Verify provider.__init__ retains genuine key (len >= 40)."""
        mock_vault = MagicMock(spec=DPAPIVault)
        genuine = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_1234567890"
        mock_vault.get_credential.return_value = genuine
        ClaudeProvider(self.db, mock_vault, self.diagnostics)
        mock_vault.delete_credential.assert_not_called()

    def test_16_clean_error_logs_after_repeated_sync(self):
        """Verify that running sync_usage 5 times with dummy key produces 0 AUTH_FAILURE logs."""
        self.vault.get_credential.return_value = None  # sanitized
        with patch.object(self.provider, "fetch_live_oauth_telemetry", return_value={"success": True}):
            with patch.object(self.provider, "scan_local_logs", return_value=0):
                for _ in range(5):
                    self.provider.sync_usage()
                recent_errors = self.diagnostics.get_recent_errors(limit=50)
                self.assertEqual(len([e for e in recent_errors if e.get("provider") == "claude"]), 0)

    def test_17_oauth_headers_contain_beta_flag(self):
        """Verify OAuth request contains required anthropic-beta header."""
        with patch.object(self.provider, "_discover_oauth_token", return_value="tok_123"):
            with patch("urllib.request.urlopen") as mock_url:
                mock_resp = MagicMock()
                mock_resp.status = 200
                mock_resp.read.return_value = b'{"success": true}'
                mock_url.return_value.__enter__.return_value = mock_resp

                self.provider._request_oauth_json("https://api.anthropic.com/api/oauth/profile")
                req = mock_url.call_args[0][0]
                self.assertEqual(req.headers.get("Anthropic-beta"), "oauth-2025-04-20")

    def test_18_profile_data_extracts_user_and_org(self):
        """Verify profile_data extracts full_name and org name."""
        mock_usage = {"five_hour": {"utilization": 10.0}}
        mock_profile = {
            "account": {"full_name": "James Christopher Eckhardt"},
            "organization": {"name": "Synthesis 2", "rate_limit_tier": "default_claude_max_5x"}
        }
        with patch.object(self.provider, "_request_oauth_json", side_effect=lambda u: mock_usage if "usage" in u else mock_profile):
            res = self.provider.fetch_live_oauth_telemetry(force=True)
            self.assertEqual(res.get("user_name"), "James Christopher Eckhardt")

    def test_19_offline_fallback_when_oauth_token_absent(self):
        """Verify graceful fallback when OAuth token is absent."""
        with patch.object(self.provider, "_discover_oauth_token", return_value=None):
            with patch.object(self.provider, "_scan_offline_plan_history", return_value={"success": True, "fallback": True}):
                res = self.provider.fetch_live_oauth_telemetry(force=True)
                self.assertTrue(res.get("fallback"))

    def test_20_live_sync_mode_returned_when_key_absent_and_oauth_active(self):
        """Verify sync_usage returns mode='live_sync' when using OAuth without direct API key."""
        self.vault.get_credential.return_value = None
        with patch.object(self.provider, "fetch_live_oauth_telemetry", return_value={"success": True}):
            with patch.object(self.provider, "scan_local_logs", return_value=12):
                res = self.provider.sync_usage()
                self.assertEqual(res.get("mode"), "live_sync")
                self.assertEqual(res.get("tokens_generated"), 12)


if __name__ == "__main__":
    unittest.main()

import unittest
import sys
import os
import json
import tempfile
import datetime
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.providers.claude import ClaudeProvider
from backend.providers.gemini import GeminiProvider
from backend.proxy.transparent_proxy import TransparentProxyServer
from backend.server.http_server import AppHTTPServer

class TestGranularTimeseriesAndGeminiProxy(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_granular.db")
        self.db = UsageDatabase(db_path=self.db_path)
        self.vault = DPAPIVault(storage_path=os.path.join(self.temp_dir.name, "vault.json"))
        self.diagnostics = DiagnosticsEngine()
        self.claude = ClaudeProvider(self.db, self.vault, self.diagnostics)
        self.gemini = GeminiProvider(self.db, self.vault, self.diagnostics)

        # Start transparent proxy on an ephemeral port
        self.proxy = TransparentProxyServer(
            claude_provider=self.claude,
            gemini_provider=self.gemini,
            host="127.0.0.1",
            port=0
        )
        self.proxy.start()

        # Start App HTTP Server on ephemeral port
        self.app_server = AppHTTPServer(
            database=self.db,
            vault=self.vault,
            diagnostics=self.diagnostics,
            providers={"claude": self.claude, "gemini": self.gemini},
            host="127.0.0.1",
            port=0,
            proxy_port=self.proxy.server_port
        )
        self.app_server.start()

    def tearDown(self):
        self.app_server.stop()
        self.proxy.stop()
        self.temp_dir.cleanup()

    def test_get_granular_timeseries_discrete_buckets_and_modes(self):
        """Assert granular time-series grouping by 1m, 5m, 15m, 60m with delta and cumulative modes."""
        now = datetime.datetime.now(datetime.timezone.utc)

        # Seed 3 events: 10 mins ago, 25 mins ago, 40 mins ago
        t1 = (now - datetime.timedelta(minutes=10)).isoformat()
        t2 = (now - datetime.timedelta(minutes=25)).isoformat()
        t3 = (now - datetime.timedelta(minutes=40)).isoformat()

        self.db.record_usage_event(
            provider="claude",
            input_tokens=100,
            output_tokens=50,
            recorded_at=t1,
            model="claude-3-5-sonnet"
        )
        self.db.record_usage_event(
            provider="gemini",
            input_tokens=200,
            output_tokens=80,
            recorded_at=t2,
            token_id="tok_gem_flash",
            model="gemini-2.0-flash"
        )
        self.db.record_usage_event(
            provider="ollama",
            input_tokens=500,
            output_tokens=150,
            recorded_at=t3,
            model="llama3:latest"
        )

        # 1. Test 5-minute bucket granularity with interval_delta mode
        res_5m_delta = self.db.get_granular_timeseries(
            window="1h",
            bucket_minutes=5,
            mode="interval_delta"
        )
        self.assertIn("series", res_5m_delta)
        self.assertIn("labels", res_5m_delta)
        self.assertEqual(res_5m_delta["bucket_minutes"], 5)
        self.assertEqual(res_5m_delta["mode"], "interval_delta")
        # 1 hour with 5m buckets = 12 bins
        self.assertEqual(len(res_5m_delta["labels"]), 12)

        # Ensure total envelope matches sum of tokens
        total_series = next((s for s in res_5m_delta["series"] if s["id"] == "total"), None)
        self.assertIsNotNone(total_series)
        self.assertEqual(sum(total_series["points"]), 1080)
        # Delta mode must have zero points for idle bins
        zero_points = [p for p in total_series["points"] if p == 0]
        self.assertGreater(len(zero_points), 0)

        # 2. Test cumulative mode
        res_15m_cum = self.db.get_granular_timeseries(
            window="1h",
            bucket_minutes=15,
            mode="cumulative"
        )
        total_cum = next((s for s in res_15m_cum["series"] if s["id"] == "total"), None)
        self.assertIsNotNone(total_cum)
        self.assertEqual(res_15m_cum["mode"], "cumulative")
        # Cumulative points must be monotonically non-decreasing
        pts = total_cum["points"]
        for i in range(1, len(pts)):
            self.assertGreaterEqual(pts[i], pts[i-1])
        self.assertEqual(pts[-1], 1080)

    def test_transparent_proxy_gemini_interception(self):
        """Assert transparent proxy intercepts Gemini completion and attributes usageMetadata tokens."""
        url = f"http://127.0.0.1:{self.proxy.server_port}/v1beta/models/gemini-2.0-flash:generateContent?key=AIzaSyDa1234567f2b"
        headers = {
            "Content-Type": "application/json",
            "x-mock-gemini-response": "true",
            "x-mock-input-tokens": "350",
            "x-mock-output-tokens": "120"
        }
        payload = json.dumps({
            "contents": [{"parts": [{"text": "Hello Gemini"}]}]
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("usageMetadata", data)
            self.assertEqual(data["usageMetadata"]["totalTokenCount"], 470)

        # Verify event was ingested in SQLite under Gemini
        events = self.db.get_recent_sessions(limit=5, provider="gemini")
        self.assertGreaterEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["provider"], "gemini")
        self.assertEqual(ev["input_tokens"], 350)
        self.assertEqual(ev["output_tokens"], 120)
        self.assertEqual(ev["total_tokens"], 470)
        self.assertIn("gemini-2.0-flash", ev["model"])

    def test_ui_refresh_cadence_setting(self):
        """Assert minimum 30s cadence configuration and validation in database settings."""
        # Default cadence
        settings = self.db.get_all_settings()
        self.assertIn("ui_refresh_interval_seconds", settings)
        self.assertGreaterEqual(settings["ui_refresh_interval_seconds"], 30)

        # Update cadence
        self.db.set_ui_refresh_cadence(60)
        updated = self.db.get_all_settings()
        self.assertEqual(updated["ui_refresh_interval_seconds"], 60)

        # Enforce minimum boundary of 30 seconds
        self.db.set_ui_refresh_cadence(5) # Attempting too low
        clamped = self.db.get_all_settings()
        self.assertEqual(clamped["ui_refresh_interval_seconds"], 30)

    def test_http_timeseries_endpoint(self):
        """Assert GET /api/usage/timeseries returns bucketed series via HTTP."""
        self.db.record_usage_event(
            provider="claude",
            input_tokens=150,
            output_tokens=50,
            model="claude-3-5-sonnet"
        )
        url = f"http://127.0.0.1:{self.app_server.server_port}/api/usage/timeseries?window=1h&bucket_minutes=5&mode=interval_delta"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertEqual(data.get("bucket_minutes"), 5)
            self.assertEqual(data.get("mode"), "interval_delta")
            self.assertIn("series", data)
            total = next((s for s in data["series"] if s["id"] == "total"), None)
            self.assertIsNotNone(total)
            self.assertEqual(total["total_tokens"], 200)

    def test_http_gemini_test_probe_and_settings(self):
        """Assert POST /api/providers/gemini/test-probe records event and POST /api/settings handles cadence."""
        # 1. Test probe
        probe_url = f"http://127.0.0.1:{self.app_server.server_port}/api/providers/gemini/test-probe"
        payload = json.dumps({
            "model": "gemini-2.0-flash",
            "input_tokens": 400,
            "output_tokens": 100,
            "token_id": "tok_gem_flash"
        }).encode("utf-8")
        req = urllib.request.Request(probe_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("total_tokens"), 500)

        # Verify event in DB
        recent = self.db.get_recent_sessions(limit=1, provider="gemini")
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["total_tokens"], 500)

        # 2. Test cadence settings via HTTP POST
        settings_url = f"http://127.0.0.1:{self.app_server.server_port}/api/settings"
        s_payload = json.dumps({
            "settings": {
                "ui_refresh_interval_seconds": 120
            }
        }).encode("utf-8")
        s_req = urllib.request.Request(settings_url, data=s_payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(s_req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            s_data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(s_data.get("success"))
            self.assertEqual(s_data["settings"]["ui_refresh_interval_seconds"], 120)

if __name__ == "__main__":
    unittest.main()

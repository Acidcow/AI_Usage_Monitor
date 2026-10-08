import unittest
import sys
import tempfile
import os
import json
import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.analytics.throughput_engine import ThroughputAnalyticsEngine
from backend.server.http_server import AppHTTPServer

class TestThroughputAnalytics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.temp_dir.name, "test_analytics.db")
        cls.db = UsageDatabase(db_path=cls.db_path)
        cls.vault = DPAPIVault(storage_path=os.path.join(cls.temp_dir.name, "vault.json"))
        cls.diagnostics = DiagnosticsEngine()
        cls.engine = ThroughputAnalyticsEngine(database=cls.db)

        # Seed sample usage events across recent hours to test rolling metrics and burst factors
        now = datetime.datetime.now(datetime.timezone.utc)
        # 1. Steady background events for claude and gemini
        for i in range(10):
            ts = (now - datetime.timedelta(minutes=i * 5)).isoformat()
            cls.db.record_usage_event(
                provider="claude",
                model="claude-3-7-sonnet",
                input_tokens=1000,
                output_tokens=300,
                session_id=f"sess_c_{i}",
                recorded_at=ts
            )

        # 2. Burst spike for gemini (high tokens in last 3 minutes)
        for i in range(5):
            ts = (now - datetime.timedelta(minutes=1)).isoformat()
            cls.db.record_usage_event(
                provider="gemini",
                model="gemini-2.0-flash",
                input_tokens=5000,
                output_tokens=2000,
                session_id=f"sess_g_spike_{i}",
                recorded_at=ts
            )

        # Set provider snapshots with quota allowances
        cls.db.update_provider_snapshot(
            provider="claude",
            tokens_remaining=120000,
            session_remaining_pct=35.0,
            weekly_remaining_pct=72.0,
            status="ACTIVE"
        )
        cls.db.update_provider_snapshot(
            provider="gemini",
            tokens_remaining=40000,
            session_remaining_pct=15.0,
            weekly_remaining_pct=65.0,
            status="ACTIVE"
        )

        cls.server = AppHTTPServer(
            database=cls.db,
            vault=cls.vault,
            diagnostics=cls.diagnostics,
            providers={},
            host="127.0.0.1",
            port=0
        )
        cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        cls.temp_dir.cleanup()

    def test_compute_rolling_averages(self):
        """Assert calculations for 1h, 24h, and 7d rolling token averages."""
        stats = self.engine.compute_throughput_metrics(provider="claude")
        self.assertIn("rolling_1h_tokens", stats)
        self.assertIn("rolling_24h_tokens", stats)
        self.assertIn("tokens_per_minute", stats)
        self.assertGreater(stats["rolling_1h_tokens"], 0)
        self.assertGreater(stats["tokens_per_minute"], 0)

    def test_burst_velocity_and_factor(self):
        """Assert detection of burst spikes and burst factor calculation."""
        metrics = self.engine.compute_throughput_metrics(provider="gemini")
        self.assertIn("peak_5m_burst_tokens", metrics)
        self.assertIn("burst_factor", metrics)
        self.assertGreater(metrics["peak_5m_burst_tokens"], 20000)
        self.assertGreater(metrics["burst_factor"], 1.5)

    def test_predictive_time_to_exhaustion(self):
        """Assert mathematical calculation of Time-To-Exhaustion (TTE)."""
        forecast = self.engine.compute_capacity_forecast()
        self.assertIn("providers", forecast)
        self.assertIn("claude", forecast["providers"])
        self.assertIn("gemini", forecast["providers"])

        gemini_fc = forecast["providers"]["gemini"]
        self.assertIn("time_to_exhaustion_minutes", gemini_fc)
        self.assertIn("severity", gemini_fc)
        self.assertIn(gemini_fc["severity"], ["CRITICAL", "WARNING", "HEALTHY"])

    def test_estate_optimization_recommendations(self):
        """Assert heuristic advisor generates actionable capacity recommendations."""
        recs = self.engine.generate_estate_recommendations()
        self.assertIsInstance(recs, list)
        self.assertGreater(len(recs), 0)
        rec_types = [r.get("type") for r in recs]
        self.assertTrue(any(t in ["LOCAL_OFFLOAD", "RATE_LIMIT_WARNING", "LOAD_BALANCING"] for t in rec_types))

    def test_api_analytics_endpoints(self):
        """Assert REST API endpoints for throughput, forecast, and recommendations."""
        import urllib.request
        port = self.server.server_port

        # 1. Throughput endpoint
        req1 = urllib.request.Request(f"http://127.0.0.1:{port}/api/analytics/throughput")
        with urllib.request.urlopen(req1, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data1 = json.loads(resp.read().decode("utf-8"))
            self.assertIn("throughput", data1)

        # 2. Forecast endpoint
        req2 = urllib.request.Request(f"http://127.0.0.1:{port}/api/analytics/forecast")
        with urllib.request.urlopen(req2, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data2 = json.loads(resp.read().decode("utf-8"))
            self.assertIn("forecast", data2)

        # 3. Recommendations endpoint
        req3 = urllib.request.Request(f"http://127.0.0.1:{port}/api/analytics/recommendations")
        with urllib.request.urlopen(req3, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data3 = json.loads(resp.read().decode("utf-8"))
            self.assertIn("recommendations", data3)

if __name__ == "__main__":
    unittest.main()

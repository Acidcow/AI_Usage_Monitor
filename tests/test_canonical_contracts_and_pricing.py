"""
Unit Tests for AIUM-1005: Canonical Data Contracts & Model-Specific Pricing Matrix.
Verifies all model tiers, cache multipliers, local cloud-savings benchmark,
and zero-dependency dataclass serialization.
"""

import unittest
import sys
import tempfile
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.contracts import (
    UsageEventContract,
    TelemetrySeriesPoint,
    TelemetrySeries,
    ProviderQuotaSnapshot,
    ThemeConfig,
    WidgetConfig,
    MODEL_PRICING_PER_M,
    calculate_event_cost,
    estimate_cloud_equivalent_savings_usd,
    resolve_pricing_rates,
)
from backend.storage.database import UsageDatabase
from backend.security.dpapi_vault import DPAPIVault
from backend.diagnostics.logging_engine import DiagnosticsEngine
from backend.providers.gemini import GeminiProvider


class TestModelPricingMatrix(unittest.TestCase):
    """Verifies all model pricing tiers, multipliers, and cost calculations."""

    def test_claude_opus_pricing(self):
        """Claude Opus 4 / 3: $15.00/M in, $75.00/M out, 1.25x write, 0.10x read."""
        rates = resolve_pricing_rates("claude", "claude-3-opus-20240229")
        self.assertEqual(rates, (15.0, 75.0, 1.25, 0.10))

        # 10k in ($0.15) + 2k out ($0.15) = $0.30
        cost = calculate_event_cost("claude", "claude-opus-4", 10_000, 2_000)
        self.assertEqual(cost, 0.30)

    def test_claude_sonnet_pricing(self):
        """Claude Sonnet 4 / 3.7 / 3.5: $3.00/M in, $15.00/M out, 1.25x write, 0.10x read."""
        rates = resolve_pricing_rates("claude", "claude-3-7-sonnet-20250219")
        self.assertEqual(rates, (3.0, 15.0, 1.25, 0.10))

        # 100k in ($0.30) + 10k out ($0.15) = $0.45
        cost = calculate_event_cost("claude", "claude-3-5-sonnet", 100_000, 10_000)
        self.assertEqual(cost, 0.45)

    def test_claude_haiku_pricing(self):
        """Claude Haiku 3.5 / 3: $0.80/M in, $4.00/M out, 1.25x write, 0.10x read."""
        rates = resolve_pricing_rates("claude", "claude-3-5-haiku-20241022")
        self.assertEqual(rates, (0.80, 4.0, 1.25, 0.10))

        # 1M in ($0.80) + 1M out ($4.00) = $4.80
        cost = calculate_event_cost("claude", "claude-3-haiku", 1_000_000, 1_000_000)
        self.assertEqual(cost, 4.80)

    def test_gemini_pro_pricing(self):
        """Gemini 2.5 Pro / 1.5 Pro: $1.25/M in, $5.00/M out, 1.0x write, 0.25x read."""
        rates = resolve_pricing_rates("gemini", "gemini-1.5-pro")
        self.assertEqual(rates, (1.25, 5.0, 1.0, 0.25))

        # 200k in ($0.25) + 100k out ($0.50) = $0.75
        cost = calculate_event_cost("gemini", "gemini-2.5-pro", 200_000, 100_000)
        self.assertEqual(cost, 0.75)

    def test_gemini_flash_pricing(self):
        """Gemini 2.5 Flash / 2.0 Flash / 1.5 Flash: $0.15/M in, $0.60/M out, 1.0x write, 0.25x read."""
        rates = resolve_pricing_rates("gemini", "gemini-2.0-flash")
        self.assertEqual(rates, (0.15, 0.60, 1.0, 0.25))

        # 1M in ($0.15) + 500k out ($0.30) = $0.45
        cost = calculate_event_cost("gemini", "gemini-2.5-flash", 1_000_000, 500_000)
        self.assertEqual(cost, 0.45)

    def test_openai_gpt4o_pricing(self):
        """OpenAI GPT-4o: $2.50/M in, $10.00/M out, 1.0x write, 0.50x read."""
        rates = resolve_pricing_rates("openai", "gpt-4o-2024-08-06")
        self.assertEqual(rates, (2.50, 10.0, 1.0, 0.50))

        cost = calculate_event_cost("openai", "gpt-4o", 100_000, 50_000)
        # 100k in ($0.25) + 50k out ($0.50) = $0.75
        self.assertEqual(cost, 0.75)

    def test_openai_gpt4o_mini_pricing(self):
        """OpenAI GPT-4o-mini: $0.15/M in, $0.60/M out, 1.0x write, 0.50x read."""
        rates = resolve_pricing_rates("openai", "gpt-4o-mini")
        self.assertEqual(rates, (0.15, 0.60, 1.0, 0.50))

        cost = calculate_event_cost("openai", "gpt-4o-mini-2024-07-18", 1_000_000, 500_000)
        self.assertEqual(cost, 0.45)

    def test_openai_o1_o3_mini_pricing(self):
        """OpenAI o1 / o3-mini: $1.10/M in, $4.40/M out, 1.0x write, 0.50x read."""
        rates_o1 = resolve_pricing_rates("openai", "o1-mini")
        rates_o3 = resolve_pricing_rates("openai", "o3-mini")
        self.assertEqual(rates_o1, (1.10, 4.40, 1.0, 0.50))
        self.assertEqual(rates_o3, (1.10, 4.40, 1.0, 0.50))

        cost = calculate_event_cost("openai", "o3-mini", 100_000, 20_000)
        # 100k in ($0.11) + 20k out ($0.088) = $0.198
        self.assertEqual(cost, 0.198)

    def test_m365_copilot_zero_cost(self):
        """M365 Copilot seat subscription evaluates to $0.00 raw token cost."""
        rates = resolve_pricing_rates("m365", "copilot-enterprise")
        self.assertEqual(rates, (0.0, 0.0, 1.0, 1.0))
        cost = calculate_event_cost("m365", "copilot", 500_000, 100_000)
        self.assertEqual(cost, 0.0)

    def test_ollama_local_zero_cost(self):
        """Ollama and local engines evaluate to $0.00 token cost."""
        for prov in ("ollama", "lmstudio", "vllm", "local", "iris", "iris_p2p"):
            rates = resolve_pricing_rates(prov, "deepseek-r1:14b")
            self.assertEqual(rates, (0.0, 0.0, 1.0, 1.0))
            cost = calculate_event_cost(prov, "qwen2.5:32b", 250_000, 75_000)
            self.assertEqual(cost, 0.0)

    def test_cloud_equivalent_savings_helper(self):
        """Cloud savings helper uses Sonnet ($3.00/M in, $15.00/M out) benchmark."""
        # 1M in ($3.00) + 1M out ($15.00) = $18.00
        savings = estimate_cloud_equivalent_savings_usd(1_000_000, 1_000_000)
        self.assertEqual(savings, 18.0)

        # 50k in ($0.15) + 10k out ($0.15) = $0.30
        savings_small = estimate_cloud_equivalent_savings_usd(50_000, 10_000)
        self.assertEqual(savings_small, 0.30)

    def test_cache_creation_multiplier_claude(self):
        """Claude cache creation carries 1.25x input rate surcharge."""
        # Sonnet base input = $3.00/M -> cache write rate = $3.75/M
        cost = calculate_event_cost(
            provider="claude",
            model="claude-3-5-sonnet",
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=1_000_000,
            cache_read_tokens=0,
        )
        self.assertEqual(cost, 3.75)

    def test_cache_read_multiplier_claude(self):
        """Claude cache read carries 0.10x input rate (90% discount)."""
        # Sonnet base input = $3.00/M -> cache read rate = $0.30/M
        cost = calculate_event_cost(
            provider="claude",
            model="claude-3-5-sonnet",
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=1_000_000,
        )
        self.assertEqual(cost, 0.30)

    def test_cache_creation_and_read_gemini(self):
        """Gemini context cache: 1.0x creation, 0.25x read."""
        # Gemini 2.0 Flash: input $0.15/M -> write $0.15/M, read $0.0375/M
        cost = calculate_event_cost(
            provider="gemini",
            model="gemini-2.0-flash",
            input_tokens=1_000_000,      # $0.15
            output_tokens=1_000_000,     # $0.60
            cache_creation_tokens=1_000_000,  # $0.15
            cache_read_tokens=1_000_000,      # $0.0375
        )
        self.assertEqual(cost, 0.9375)

    def test_case_insensitivity_and_partial_matching(self):
        """Model resolution handles uppercase and arbitrary prefix/suffix decorators."""
        rates_upper = resolve_pricing_rates("CLAUDE", "ANTHROPIC.CLAUDE-3-7-SONNET-V1:0")
        self.assertEqual(rates_upper, (3.0, 15.0, 1.25, 0.10))

        rates_gem = resolve_pricing_rates("GOOGLE", "models/gemini-2.5-pro-exp-02")
        self.assertEqual(rates_gem, (1.25, 5.0, 1.0, 0.25))

        rates_gpt = resolve_pricing_rates("OpenAI", "GPT-4O-MINI-LATEST")
        self.assertEqual(rates_gpt, (0.15, 0.60, 1.0, 0.50))


class TestCanonicalDataContracts(unittest.TestCase):
    """Verifies dataclass construction, validation, auto-calculations, and serialization."""

    def test_usage_event_contract_auto_sum_and_pricing(self):
        """UsageEventContract automatically totals tokens and calculates cost if omitted."""
        evt = UsageEventContract(
            provider="claude",
            model="claude-3-5-sonnet",
            input_tokens=100_000,
            output_tokens=20_000,
            cache_creation_tokens=10_000,
            cache_read_tokens=40_000,
        )
        # Total tokens: 100k + 20k + 10k + 40k = 170k
        self.assertEqual(evt.total_tokens, 170_000)
        # Cost: 100k*$3/M ($0.30) + 20k*$15/M ($0.30) + 10k*$3.75/M ($0.0375) + 40k*$0.30/M ($0.012) = $0.6495
        self.assertEqual(evt.cost_usd, 0.6495)
        self.assertIsNotNone(evt.recorded_at)

        # Serialization
        d = evt.to_dict()
        self.assertEqual(d["total_tokens"], 170_000)
        self.assertEqual(d["cost_usd"], 0.6495)

        # Deserialization
        reconstructed = UsageEventContract.from_dict(d)
        self.assertEqual(reconstructed.provider, "claude")
        self.assertEqual(reconstructed.total_tokens, 170_000)
        self.assertEqual(reconstructed.cost_usd, 0.6495)

    def test_usage_event_contract_explicit_cost_preserved(self):
        """Explicit cost_usd is preserved and not overwritten."""
        evt = UsageEventContract(
            provider="claude",
            model="claude-3-5-sonnet",
            input_tokens=100_000,
            output_tokens=20_000,
            cost_usd=1.2345,
        )
        self.assertEqual(evt.cost_usd, 1.2345)

    def test_telemetry_series_point(self):
        """TelemetrySeriesPoint serializes and deserializes correctly."""
        pt = TelemetrySeriesPoint(
            bucket_utc="2026-11-07T12:00:00Z",
            label="12:00 UTC",
            tokens=45000,
            cost_usd=0.135,
            requests=3,
            is_cumulative=False,
        )
        d = pt.to_dict()
        self.assertEqual(d["tokens"], 45000)
        self.assertEqual(d["cost_usd"], 0.135)

        pt2 = TelemetrySeriesPoint.from_dict(d)
        self.assertEqual(pt2.bucket_utc, "2026-11-07T12:00:00Z")
        self.assertEqual(pt2.tokens, 45000)

    def test_telemetry_series_auto_aggregation(self):
        """TelemetrySeries aggregates points and sums tokens and cost."""
        pts = [
            TelemetrySeriesPoint(bucket_utc="2026-11-07T10:00:00Z", tokens=1000, cost_usd=0.01),
            TelemetrySeriesPoint(bucket_utc="2026-11-07T11:00:00Z", tokens=2000, cost_usd=0.02),
            TelemetrySeriesPoint(bucket_utc="2026-11-07T12:00:00Z", tokens=3000, cost_usd=0.03),
        ]
        series = TelemetrySeries(
            series_id="ser_claude_hourly",
            label="Claude Hourly",
            provider="claude",
            points=pts,
        )
        self.assertEqual(series.total_tokens, 6000)
        self.assertEqual(series.total_cost_usd, 0.06)

        d = series.to_dict()
        self.assertEqual(len(d["points"]), 3)
        self.assertEqual(d["total_tokens"], 6000)

        reconstructed = TelemetrySeries.from_dict(d)
        self.assertEqual(reconstructed.series_id, "ser_claude_hourly")
        self.assertEqual(reconstructed.total_tokens, 6000)

    def test_provider_quota_snapshot(self):
        """ProviderQuotaSnapshot holds status, pacing, burn rate, and reset times."""
        snap = ProviderQuotaSnapshot(
            provider="claude",
            status="ACTIVE",
            session_used_pct=34.5,
            session_remaining_pct=65.5,
            weekly_used_pct=12.0,
            weekly_remaining_pct=88.0,
            session_reset_str="2h 15m",
            weekly_reset_str="4d 10h",
            burn_rate_tok_per_min=124.5,
            pacing_status="NORMAL",
        )
        d = snap.to_dict()
        self.assertEqual(d["session_remaining_pct"], 65.5)
        self.assertEqual(d["pacing_status"], "NORMAL")

        reconstructed = ProviderQuotaSnapshot.from_dict(d)
        self.assertEqual(reconstructed.provider, "claude")
        self.assertEqual(reconstructed.burn_rate_tok_per_min, 124.5)

    def test_theme_config(self):
        """ThemeConfig provides UI styling parameters."""
        theme = ThemeConfig(theme_name="solarized_dark", primary_color="#268bd2")
        d = theme.to_dict()
        self.assertEqual(d["theme_name"], "solarized_dark")
        self.assertEqual(d["primary_color"], "#268bd2")

        reconstructed = ThemeConfig.from_dict(d)
        self.assertEqual(reconstructed.theme_name, "solarized_dark")

    def test_widget_config(self):
        """WidgetConfig controls floating desktop widget geometry and options."""
        w = WidgetConfig(
            widget_id="main_widget",
            x=200,
            y=150,
            width=400,
            height=300,
            opacity=0.90,
            snapped_edge="top-right",
            refresh_interval_ms=5000,
            compact_mode=True,
        )
        d = w.to_dict()
        self.assertEqual(d["snapped_edge"], "top-right")
        self.assertEqual(d["refresh_interval_ms"], 5000)
        self.assertTrue(d["compact_mode"])

        reconstructed = WidgetConfig.from_dict(d)
        self.assertEqual(reconstructed.widget_id, "main_widget")
        self.assertEqual(reconstructed.snapped_edge, "top-right")

    def test_package_exports(self):
        """backend.contracts exports all specified contracts and pricing routines."""
        import backend.contracts as contracts
        expected_symbols = [
            "UsageEventContract",
            "TelemetrySeriesPoint",
            "TelemetrySeries",
            "ProviderQuotaSnapshot",
            "ThemeConfig",
            "WidgetConfig",
            "MODEL_PRICING_PER_M",
            "calculate_event_cost",
            "estimate_cloud_equivalent_savings_usd",
            "resolve_pricing_rates",
        ]
        for sym in expected_symbols:
            self.assertTrue(hasattr(contracts, sym), f"Missing exported symbol: {sym}")


class TestProviderAndReportingIntegration(unittest.TestCase):
    """Verifies GeminiProvider and ReportingEngine integration with pricing matrix."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_contracts_integration.db")
        self.db = UsageDatabase(db_path=self.db_path)
        self.vault = DPAPIVault(storage_path=os.path.join(self.temp_dir.name, "vault.json"))
        self.diagnostics = DiagnosticsEngine()
        self.gemini = GeminiProvider(self.db, self.vault, self.diagnostics)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_gemini_provider_proxy_ingestion_uses_pricing(self):
        """GeminiProvider.ingest_proxy_interaction computes pricing with model rate matrix."""
        # For gemini-2.0-flash: in $0.15/M, out $0.60/M
        # 100k in ($0.015) + 50k out ($0.030) = $0.045
        evt_id = self.gemini.ingest_proxy_interaction(
            model="gemini-2.0-flash",
            input_tokens=100_000,
            output_tokens=50_000,
        )
        self.assertTrue(evt_id.startswith("evt_"))

        sessions = self.db.get_recent_sessions(limit=1, provider="gemini")
        self.assertEqual(len(sessions), 1)
        ev = sessions[0]
        self.assertAlmostEqual(ev["estimated_cost"], 0.045, places=5)

    def test_reporting_engine_local_savings_calculation(self):
        """ReportingEngine computes estimated_savings_usd for Ollama using Sonnet benchmark."""
        self.db.record_usage_event(
            provider="ollama",
            model="llama3:8b",
            input_tokens=100_000,
            output_tokens=50_000,
            session_id="ollama_sess_1",
            estimated_cost=0.0,
        )
        report = self.db.query_historical_report(provider="ollama")
        self.assertTrue(report.get("records"))
        rec = report["records"][0]
        self.assertEqual(rec["total_cost_usd"], 0.0)
        # Blended frontier savings benchmark ($6.00/1M): 150k * $6/M = $0.90
        self.assertAlmostEqual(rec["estimated_savings_usd"], 0.90, places=2)
        self.assertAlmostEqual(rec["net_cost_usd"], -0.90, places=2)


if __name__ == "__main__":
    unittest.main()

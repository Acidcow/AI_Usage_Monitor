"""
Canonical Data Contracts & Pricing Matrix (AIUM-1005)
Zero-dependency dataclasses and pricing helpers for AI Usage Monitor.
"""

from backend.contracts.models import (
    UsageEventContract,
    TelemetrySeriesPoint,
    TelemetrySeries,
    ProviderQuotaSnapshot,
    ThemeConfig,
    WidgetConfig,
)
from backend.contracts.pricing import (
    MODEL_PRICING_PER_M,
    RateTuple,
    calculate_event_cost,
    estimate_cloud_equivalent_savings_usd,
    resolve_pricing_rates,
)

__all__ = [
    "UsageEventContract",
    "TelemetrySeriesPoint",
    "TelemetrySeries",
    "ProviderQuotaSnapshot",
    "ThemeConfig",
    "WidgetConfig",
    "MODEL_PRICING_PER_M",
    "RateTuple",
    "calculate_event_cost",
    "estimate_cloud_equivalent_savings_usd",
    "resolve_pricing_rates",
]

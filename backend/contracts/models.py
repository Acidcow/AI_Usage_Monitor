"""
AI Usage Monitor - Canonical Data Contracts (AIUM-1005)
Zero-dependency, typed stdlib dataclasses for usage telemetry, series, quotas, and UI configs.
"""

from dataclasses import dataclass, field, asdict
import datetime
from typing import Any, Dict, List, Optional


@dataclass
class UsageEventContract:
    """
    Canonical data contract for an individual AI token usage event across all providers.
    """
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""
    session_id: str = ""
    external_id: Optional[str] = None
    source: str = "direct"
    access_route: str = "direct"
    account_id: str = ""
    node_id: Optional[str] = None
    recorded_at: Optional[str] = None

    def __post_init__(self) -> None:
        if self.total_tokens == 0:
            self.total_tokens = (
                self.input_tokens
                + self.output_tokens
                + self.cache_creation_tokens
                + self.cache_read_tokens
            )
        if self.cost_usd == 0.0 and (self.input_tokens or self.output_tokens or self.cache_creation_tokens or self.cache_read_tokens):
            from backend.contracts.pricing import calculate_event_cost
            computed = calculate_event_cost(
                provider=self.provider,
                model=self.model,
                input_tokens=self.input_tokens,
                output_tokens=self.output_tokens,
                cache_creation_tokens=self.cache_creation_tokens,
                cache_read_tokens=self.cache_read_tokens,
            )
            if computed > 0.0:
                self.cost_usd = computed
        if self.recorded_at is None:
            self.recorded_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serializes contract instance to a Python dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UsageEventContract":
        """Reconstructs contract instance from a dictionary."""
        return cls(
            provider=str(data.get("provider") or ""),
            input_tokens=int(data.get("input_tokens") or 0),
            output_tokens=int(data.get("output_tokens") or 0),
            total_tokens=int(data.get("total_tokens") or 0),
            cache_creation_tokens=int(data.get("cache_creation_tokens") or 0),
            cache_read_tokens=int(data.get("cache_read_tokens") or 0),
            cost_usd=float(data.get("cost_usd") if data.get("cost_usd") is not None else (data.get("estimated_cost") or 0.0)),
            model=str(data.get("model") or ""),
            session_id=str(data.get("session_id") or ""),
            external_id=data.get("external_id"),
            source=str(data.get("source") or "direct"),
            access_route=str(data.get("access_route") or "direct"),
            account_id=str(data.get("account_id") or ""),
            node_id=data.get("node_id"),
            recorded_at=data.get("recorded_at"),
        )


@dataclass
class TelemetrySeriesPoint:
    """
    Single discrete time bucket or snapshot point in an analytical telemetry series.
    """
    bucket_utc: str
    label: str = ""
    tokens: int = 0
    cost_usd: float = 0.0
    requests: int = 0
    is_cumulative: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serializes point instance to a Python dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TelemetrySeriesPoint":
        """Reconstructs point instance from a dictionary."""
        return cls(
            bucket_utc=str(data.get("bucket_utc") or ""),
            label=str(data.get("label") or ""),
            tokens=int(data.get("tokens") or 0),
            cost_usd=float(data.get("cost_usd") or 0.0),
            requests=int(data.get("requests") or 0),
            is_cumulative=bool(data.get("is_cumulative", False)),
        )


@dataclass
class TelemetrySeries:
    """
    Collection of ordered telemetry points representing token or cost progression over time.
    """
    series_id: str
    label: str
    provider: str = ""
    scope: str = "global"
    color: str = "#4F46E5"
    points: List[TelemetrySeriesPoint] = field(default_factory=list)
    total_tokens: int = 0
    total_cost_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.points:
            normalized_points: List[TelemetrySeriesPoint] = []
            for pt in self.points:
                if isinstance(pt, dict):
                    normalized_points.append(TelemetrySeriesPoint.from_dict(pt))
                else:
                    normalized_points.append(pt)
            self.points = normalized_points

            if self.total_tokens == 0:
                self.total_tokens = sum(p.tokens for p in self.points)
            if self.total_cost_usd == 0.0:
                self.total_cost_usd = round(sum(p.cost_usd for p in self.points), 6)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes series instance to a Python dictionary."""
        return {
            "series_id": self.series_id,
            "label": self.label,
            "provider": self.provider,
            "scope": self.scope,
            "color": self.color,
            "points": [p.to_dict() if hasattr(p, "to_dict") else p for p in self.points],
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TelemetrySeries":
        """Reconstructs series instance from a dictionary."""
        raw_pts = data.get("points") or []
        pts = [
            TelemetrySeriesPoint.from_dict(p) if isinstance(p, dict) else p
            for p in raw_pts
        ]
        return cls(
            series_id=str(data.get("series_id") or ""),
            label=str(data.get("label") or ""),
            provider=str(data.get("provider") or ""),
            scope=str(data.get("scope") or "global"),
            color=str(data.get("color") or "#4F46E5"),
            points=pts,
            total_tokens=int(data.get("total_tokens") or 0),
            total_cost_usd=float(data.get("total_cost_usd") or 0.0),
        )


@dataclass
class ProviderQuotaSnapshot:
    """
    Standardized snapshot representing current provider quota, session/weekly balance,
    burn rate, and pacing status.
    """
    provider: str
    status: str = "ACTIVE"
    session_used_pct: float = 0.0
    session_remaining_pct: float = 100.0
    weekly_used_pct: float = 0.0
    weekly_remaining_pct: float = 100.0
    session_reset_str: str = ""
    weekly_reset_str: str = ""
    burn_rate_tok_per_min: float = 0.0
    pacing_status: str = "NORMAL"

    def to_dict(self) -> Dict[str, Any]:
        """Serializes quota snapshot instance to a Python dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProviderQuotaSnapshot":
        """Reconstructs quota snapshot instance from a dictionary."""
        return cls(
            provider=str(data.get("provider") or ""),
            status=str(data.get("status") or "ACTIVE"),
            session_used_pct=float(data.get("session_used_pct") or 0.0),
            session_remaining_pct=float(data.get("session_remaining_pct") or 100.0),
            weekly_used_pct=float(data.get("weekly_used_pct") or 0.0),
            weekly_remaining_pct=float(data.get("weekly_remaining_pct") or 100.0),
            session_reset_str=str(data.get("session_reset_str") or ""),
            weekly_reset_str=str(data.get("weekly_reset_str") or ""),
            burn_rate_tok_per_min=float(data.get("burn_rate_tok_per_min") or 0.0),
            pacing_status=str(data.get("pacing_status") or "NORMAL"),
        )


@dataclass
class ThemeConfig:
    """
    Appearance and color palette styling configuration for desktop widgets and dashboard.
    """
    theme_name: str = "dark"
    primary_color: str = "#4F46E5"
    background_color: str = "#0F172A"
    card_bg_color: str = "#1E293B"
    text_color: str = "#F8FAFC"
    accent_color: str = "#38BDF8"
    border_color: str = "#334155"
    font_family: str = "Segoe UI, Inter, sans-serif"

    def to_dict(self) -> Dict[str, Any]:
        """Serializes theme config instance to a Python dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThemeConfig":
        """Reconstructs theme config instance from a dictionary."""
        return cls(
            theme_name=str(data.get("theme_name") or "dark"),
            primary_color=str(data.get("primary_color") or "#4F46E5"),
            background_color=str(data.get("background_color") or "#0F172A"),
            card_bg_color=str(data.get("card_bg_color") or "#1E293B"),
            text_color=str(data.get("text_color") or "#F8FAFC"),
            accent_color=str(data.get("accent_color") or "#38BDF8"),
            border_color=str(data.get("border_color") or "#334155"),
            font_family=str(data.get("font_family") or "Segoe UI, Inter, sans-serif"),
        )


@dataclass
class WidgetConfig:
    """
    Positioning, sizing, opacity, and refresh properties for floating desktop widgets.
    """
    widget_id: str = "desktop_mini"
    enabled: bool = True
    x: int = 100
    y: int = 100
    width: int = 320
    height: int = 240
    opacity: float = 0.95
    always_on_top: bool = True
    snapped_edge: Optional[str] = None
    refresh_interval_ms: int = 10000
    show_sparklines: bool = True
    compact_mode: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serializes widget config instance to a Python dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WidgetConfig":
        """Reconstructs widget config instance from a dictionary."""
        return cls(
            widget_id=str(data.get("widget_id") or "desktop_mini"),
            enabled=bool(data.get("enabled", True)),
            x=int(data.get("x", 100)),
            y=int(data.get("y", 100)),
            width=int(data.get("width", 320)),
            height=int(data.get("height", 240)),
            opacity=float(data.get("opacity", 0.95)),
            always_on_top=bool(data.get("always_on_top", True)),
            snapped_edge=data.get("snapped_edge"),
            refresh_interval_ms=int(data.get("refresh_interval_ms", 10000)),
            show_sparklines=bool(data.get("show_sparklines", True)),
            compact_mode=bool(data.get("compact_mode", False)),
        )

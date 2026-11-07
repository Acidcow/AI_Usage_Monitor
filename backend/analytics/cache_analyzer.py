"""
AI Usage Monitor - Prompt Cache Efficiency Analytics & TTL Keep-Alive Engine (AIUM-1009)
Zero external dependencies. Python 3 standard library only.
"""

import datetime
from typing import Dict, Any, List, Optional

from backend.contracts.pricing import resolve_pricing_rates

# Anthropic ephemeral prompt cache TTL in seconds (5 minutes)
ANTHROPIC_CACHE_TTL_SECONDS = 300


def parse_iso_utc_timestamp(ts_str: str) -> datetime.datetime:
    """
    Parses an ISO 8601 timestamp string into a timezone-aware UTC datetime.
    Handles 'Z' suffix, space separators, and microseconds.
    """
    ts = str(ts_str).strip()
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    if " " in ts and "T" not in ts:
        ts = ts.replace(" ", "T")
    try:
        dt = datetime.datetime.fromisoformat(ts)
    except Exception:
        dt = datetime.datetime.now(datetime.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


class PromptCacheAnalyzer:
    """
    Analyzes prompt caching efficiency, write surcharges, read savings,
    ephemeral TTL keep-alive countdowns, and session cache metrics.
    """

    def __init__(self, db):
        self.db = db

    def _fetch_usage_events(
        self,
        provider: Optional[str] = "claude",
        hours: int = 24,
        now: Optional[datetime.datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Queries usage_events from the database for the given time window and provider.
        """
        ref_now = now or datetime.datetime.now(datetime.timezone.utc)
        query = (
            "SELECT input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens, "
            "model, session_id, recorded_at, provider "
            "FROM usage_events"
        )
        params: List[Any] = []
        conditions: List[str] = []

        if hours and hours > 0:
            cutoff = (ref_now - datetime.timedelta(hours=hours)).isoformat()
            conditions.append("recorded_at >= ?")
            params.append(cutoff)

        if provider and provider.lower() not in ("all", "*"):
            conditions.append("LOWER(provider) = ?")
            params.append(provider.lower())

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY recorded_at DESC"

        # Resilient query execution supporting UsageDatabase, mocks, or direct connections
        if hasattr(self.db, "_lock"):
            with self.db._lock:
                conn = self.db._get_connection()
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = [dict(r) for r in cursor.fetchall()]
                conn.close()
                return rows
        elif hasattr(self.db, "_get_connection"):
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        elif hasattr(self.db, "cursor"):
            cursor = self.db.cursor()
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]
        elif hasattr(self.db, "execute"):
            cursor = self.db.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]
        return []

    def analyze_cache_efficiency(
        self,
        provider: Optional[str] = "claude",
        hours: int = 24,
        now: Optional[datetime.datetime] = None,
    ) -> Dict[str, Any]:
        """
        Queries usage_events for the specified time window, computing:
        - total_input_tokens, total_cache_creation_tokens, total_cache_read_tokens
        - cache_hit_ratio_pct = round((cache_read / (input + cache_creation + cache_read)) * 100, 1)
        - cache_write_surcharge_usd = extra 0.25x cost paid to write cache
        - gross_cache_read_savings_usd = 0.90x discount saved on cache reads
        - net_cache_savings_usd = round(gross - surcharge, 4)
        - break_even_achieved = bool(net >= 0 and total_cache_read_tokens > 0)
        - ttl_status = ephemeral 300s TTL countdown from most recent cache touch
        - efficiency_grade = 'A+', 'A', 'B', 'C', or 'N/A'
        """
        ref_now = now or datetime.datetime.now(datetime.timezone.utc)
        rows = self._fetch_usage_events(provider=provider, hours=hours, now=ref_now)

        total_input_tokens = 0
        total_output_tokens = 0
        total_cache_creation_tokens = 0
        total_cache_read_tokens = 0

        total_write_surcharge_usd = 0.0
        total_read_savings_usd = 0.0

        most_recent_cache_touch_ts: Optional[str] = None

        for r in rows:
            in_tok = int(r.get("input_tokens") or 0)
            out_tok = int(r.get("output_tokens") or 0)
            cc_tok = int(r.get("cache_creation_tokens") or 0)
            cr_tok = int(r.get("cache_read_tokens") or 0)

            total_input_tokens += in_tok
            total_output_tokens += out_tok
            total_cache_creation_tokens += cc_tok
            total_cache_read_tokens += cr_tok

            # Track most recent cache activity event
            if (cc_tok > 0 or cr_tok > 0) and most_recent_cache_touch_ts is None:
                most_recent_cache_touch_ts = r.get("recorded_at")

            # Resolve per-event pricing rates
            event_prov = r.get("provider") or provider or "claude"
            event_model = r.get("model") or ""
            rates = resolve_pricing_rates(event_prov, event_model)
            rate_per_token = rates[0] / 1_000_000.0

            # 0.25x creation surcharge, 0.90x read discount savings
            total_write_surcharge_usd += cc_tok * rate_per_token * 0.25
            total_read_savings_usd += cr_tok * rate_per_token * 0.90

        total_prompt_tokens = (
            total_input_tokens + total_cache_creation_tokens + total_cache_read_tokens
        )
        if total_prompt_tokens > 0:
            cache_hit_ratio_pct = round(
                (total_cache_read_tokens / total_prompt_tokens) * 100.0, 1
            )
        else:
            cache_hit_ratio_pct = 0.0

        cache_write_surcharge_usd = round(total_write_surcharge_usd, 4)
        gross_cache_read_savings_usd = round(total_read_savings_usd, 4)
        net_cache_savings_usd = round(
            gross_cache_read_savings_usd - cache_write_surcharge_usd, 4
        )

        break_even_achieved = bool(
            net_cache_savings_usd >= 0 and total_cache_read_tokens > 0
        )

        # TTL Status Calculation (Anthropic Ephemeral 300-second TTL)
        if most_recent_cache_touch_ts:
            last_touch_dt = parse_iso_utc_timestamp(most_recent_cache_touch_ts)
            seconds_since_touch = max(
                0.0, (ref_now - last_touch_dt).total_seconds()
            )
            ttl_remaining_seconds = max(
                0, int(round(ANTHROPIC_CACHE_TTL_SECONDS - seconds_since_touch))
            )
            is_warm = ttl_remaining_seconds > 0
            mins = int(ttl_remaining_seconds // 60)
            secs = int(ttl_remaining_seconds % 60)
            ttl_formatted = f"{mins}m {secs}s"
            ttl_status = {
                "is_warm": is_warm,
                "ttl_remaining_seconds": ttl_remaining_seconds,
                "ttl_formatted": ttl_formatted,
                "last_touch_utc": most_recent_cache_touch_ts,
            }
        else:
            ttl_status = {
                "is_warm": False,
                "ttl_remaining_seconds": 0,
                "ttl_formatted": "0m 0s",
                "last_touch_utc": None,
            }

        # Efficiency Grade
        if cache_hit_ratio_pct >= 75.0:
            efficiency_grade = "A+"
        elif cache_hit_ratio_pct >= 50.0:
            efficiency_grade = "A"
        elif cache_hit_ratio_pct >= 25.0:
            efficiency_grade = "B"
        elif cache_hit_ratio_pct > 0.0:
            efficiency_grade = "C"
        else:
            efficiency_grade = "N/A"

        return {
            "provider": provider,
            "hours": hours,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_cache_creation_tokens": total_cache_creation_tokens,
            "total_cache_read_tokens": total_cache_read_tokens,
            "total_tokens": (
                total_input_tokens
                + total_output_tokens
                + total_cache_creation_tokens
                + total_cache_read_tokens
            ),
            "cache_hit_ratio_pct": cache_hit_ratio_pct,
            "cache_write_surcharge_usd": cache_write_surcharge_usd,
            "gross_cache_read_savings_usd": gross_cache_read_savings_usd,
            "net_cache_savings_usd": net_cache_savings_usd,
            "break_even_achieved": break_even_achieved,
            "ttl_status": ttl_status,
            "efficiency_grade": efficiency_grade,
            "event_count": len(rows),
        }

    def enrich_session_cache_metrics(
        self, session_row: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Enriches a session row with:
        - cache_hit_ratio_pct
        - net_cache_savings_usd
        - cache_badge_label
        """
        row = dict(session_row)
        in_tok = int(row.get("input_tokens") or 0)
        cc_tok = int(row.get("cache_creation_tokens") or 0)
        cr_tok = int(row.get("cache_read_tokens") or 0)

        denom = in_tok + cc_tok + cr_tok
        hit_ratio = round((cr_tok / denom) * 100.0, 1) if denom > 0 else 0.0

        prov = row.get("provider") or "claude"
        model = row.get("model") or ""
        rates = resolve_pricing_rates(prov, model)
        rate_per_token = rates[0] / 1_000_000.0

        surcharge = cc_tok * rate_per_token * 0.25
        savings = cr_tok * rate_per_token * 0.90
        net_savings = round(savings - surcharge, 4)

        if cr_tok == 0 and cc_tok == 0:
            badge_label = "No Cache"
        elif hit_ratio >= 75.0:
            badge_label = "Optimal (A+)"
        elif hit_ratio >= 50.0:
            badge_label = "High (A)"
        elif hit_ratio >= 25.0:
            badge_label = "Moderate (B)"
        elif hit_ratio > 0.0:
            badge_label = "Low (C)"
        else:
            badge_label = "Warmup"

        session_row["cache_hit_ratio_pct"] = hit_ratio
        session_row["net_cache_savings_usd"] = net_savings
        session_row["cache_badge_label"] = badge_label

        row["cache_hit_ratio_pct"] = hit_ratio
        row["net_cache_savings_usd"] = net_savings
        row["cache_badge_label"] = badge_label
        return row

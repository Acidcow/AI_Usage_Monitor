"""
AI Usage Monitor - Estate Throughput, Burst Performance & Capacity Analytics Engine.
Zero external dependencies. Python 3 standard library only.
"""

import datetime
import math
from typing import Dict, Any, List, Optional

class ThroughputAnalyticsEngine:
    """
    Computes mathematical operational metrics across AI providers:
    - Rolling token averages (1h, 24h, 7d).
    - Peak 5-minute burst velocity and burst ratio.
    - Predictive quota depletion (Time-To-Exhaustion - TTE).
    - Heuristic estate optimization recommendations.
    """

    def __init__(self, database):
        self.db = database

    def compute_throughput_metrics(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """
        Calculates rolling consumption averages, tokens/min, requests/min,
        and sliding-window peak burst factors.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        h1_cutoff = (now - datetime.timedelta(hours=1)).isoformat()
        h24_cutoff = (now - datetime.timedelta(hours=24)).isoformat()
        d7_cutoff = (now - datetime.timedelta(days=7)).isoformat()
        m5_cutoff = (now - datetime.timedelta(minutes=5)).isoformat()
        m15_cutoff = (now - datetime.timedelta(minutes=15)).isoformat()

        with self.db._lock:
            conn = self.db._get_connection()
            cursor = conn.cursor()

            base_query = "SELECT total_tokens, request_count, recorded_at, provider, model FROM usage_events WHERE recorded_at >= ?"
            params = [d7_cutoff]
            if provider:
                base_query += " AND provider = ?"
                params.append(provider.lower())

            cursor.execute(base_query, params)
            events = [dict(r) for r in cursor.fetchall()]
            conn.close()

        # Group by time windows
        tokens_1h = 0
        requests_1h = 0
        tokens_24h = 0
        requests_24h = 0
        tokens_7d = 0
        requests_7d = 0
        tokens_15m = 0
        tokens_5m = 0

        # Bucket by 5-minute windows for burst profiling
        five_min_buckets: Dict[str, int] = {}

        for ev in events:
            rec = ev.get("recorded_at", "")
            tok = int(ev.get("total_tokens", 0) or 0)
            req = int(ev.get("request_count", 1) or 1)

            tokens_7d += tok
            requests_7d += req

            if rec >= h24_cutoff:
                tokens_24h += tok
                requests_24h += req

            if rec >= h1_cutoff:
                tokens_1h += tok
                requests_1h += req

                # 5-minute bucket key (slice up to minute rounded to 5)
                try:
                    dt = datetime.datetime.fromisoformat(rec.replace("Z", "+00:00"))
                    b_min = (dt.minute // 5) * 5
                    b_key = f"{dt.hour:02d}:{b_min:02d}"
                    five_min_buckets[b_key] = five_min_buckets.get(b_key, 0) + tok
                except Exception:
                    pass

            if rec >= m15_cutoff:
                tokens_15m += tok

            if rec >= m5_cutoff:
                tokens_5m += tok

        # Calculate velocities
        tokens_per_min = round(tokens_15m / 15.0, 1) if tokens_15m > 0 else (round(tokens_1h / 60.0, 1) if tokens_1h > 0 else 0.0)
        requests_per_min = round(requests_1h / 60.0, 2) if requests_1h > 0 else 0.0

        # Burst Factor: max 5-min bucket tokens divided by average 5-min baseline in past hour
        peak_5m = max(five_min_buckets.values()) if five_min_buckets else tokens_5m
        avg_5m_baseline = max(1.0, float(tokens_1h) / 12.0)
        burst_factor = round(peak_5m / avg_5m_baseline, 2) if peak_5m > 0 else 1.0

        return {
            "provider": provider or "all",
            "rolling_1h_tokens": tokens_1h,
            "rolling_1h_requests": requests_1h,
            "rolling_24h_tokens": tokens_24h,
            "rolling_24h_requests": requests_24h,
            "rolling_7d_tokens": tokens_7d,
            "rolling_7d_requests": requests_7d,
            "tokens_per_minute": tokens_per_min,
            "requests_per_minute": requests_per_min,
            "peak_5m_burst_tokens": peak_5m,
            "burst_factor": burst_factor,
            "is_bursting": bool(burst_factor >= 2.0),
            "sample_event_count": len(events)
        }

    def compute_capacity_forecast(self) -> Dict[str, Any]:
        """
        Projects Time-To-Exhaustion (TTE) for active quotas based on current token velocity.
        """
        comp = self.db.get_comparative_metrics()
        prov_map = comp.get("providers", {})
        forecasts = {}

        for p_key, p_data in prov_map.items():
            metrics = self.compute_throughput_metrics(provider=p_key)
            vel = max(0.1, metrics["tokens_per_minute"])

            sess_rem_pct = float(p_data.get("session_balance_remaining_pct", 100.0) or 100.0)
            daily_allowance = float(p_data.get("daily_allowance", 500000) or 500000)
            # Estimate tokens remaining in current session window
            est_tokens_rem = max(0.0, (sess_rem_pct / 100.0) * daily_allowance)

            # Time to exhaustion in minutes
            if vel > 0:
                tte_mins = round(est_tokens_rem / vel, 1)
            else:
                tte_mins = 9999.0

            # Severity classification
            if sess_rem_pct <= 15.0 or tte_mins <= 60.0:
                severity = "CRITICAL"
                msg = f"Critical exhaustion risk: {sess_rem_pct:.1f}% allowance remaining ({tte_mins:.0f} mins at current velocity)"
            elif sess_rem_pct <= 35.0 or tte_mins <= 180.0:
                severity = "WARNING"
                msg = f"Elevated usage rate: {sess_rem_pct:.1f}% allowance remaining (est. {tte_mins:.0f} mins)"
            else:
                severity = "HEALTHY"
                msg = f"Quota sustainable: {sess_rem_pct:.1f}% remaining"

            forecasts[p_key] = {
                "provider": p_key,
                "session_remaining_pct": sess_rem_pct,
                "weekly_remaining_pct": float(p_data.get("weekly_balance_remaining_pct", 100.0) or 100.0),
                "tokens_per_minute": vel,
                "estimated_tokens_remaining": int(est_tokens_rem),
                "time_to_exhaustion_minutes": tte_mins,
                "time_to_exhaustion_hours": round(tte_mins / 60.0, 1),
                "severity": severity,
                "alert_message": msg,
                "reset_epoch": p_data.get("reset_epoch")
            }

        return {
            "forecast": forecasts,
            "providers": forecasts,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

    def generate_estate_recommendations(self) -> List[Dict[str, Any]]:
        """
        Analyzes estate workload patterns and generates proactive heuristic recommendations:
        - Workload offloading to local Ollama.
        - Approaching rate limit alerts.
        - Key load-balancing suggestions.
        """
        recs = []
        comp = self.db.get_comparative_metrics()
        prov_map = comp.get("providers", {})
        forecasts = self.compute_capacity_forecast()["providers"]

        # 1. Check for exhaustion risks
        for p_key, fc in forecasts.items():
            if fc["severity"] in ["CRITICAL", "WARNING"]:
                recs.append({
                    "id": f"rec_exhaust_{p_key}",
                    "type": "RATE_LIMIT_WARNING",
                    "priority": "HIGH" if fc["severity"] == "CRITICAL" else "MEDIUM",
                    "provider": p_key,
                    "title": f"Protect {p_key.title()} Quota from Depletion",
                    "description": fc["alert_message"],
                    "action_label": "Calibrate Limits" if p_key == "claude" else "Configure Key Rotation",
                    "potential_savings_usd": 0.0
                })

        # 2. Check for local Ollama offloading opportunity
        cloud_tokens_today = sum(
            p_data.get("tokens_today", 0) for p_k, p_data in prov_map.items() if p_k != "ollama"
        )
        if cloud_tokens_today >= 5000:
            potential_savings = round((cloud_tokens_today / 1000000.0) * 6.00, 2)
            recs.append({
                "id": "rec_local_offload",
                "type": "LOCAL_OFFLOAD",
                "priority": "MEDIUM",
                "provider": "ollama",
                "title": "Delegate Routine Tasks to Ollama Local Engine",
                "description": f"You have consumed {cloud_tokens_today:,} cloud tokens today. Routing repetitive coding/summarization tasks to local Ollama (Llama 3.2 / Qwen 2.5) saves ~$6.00/M tokens with zero cloud quota impact.",
                "action_label": "Explore Local Models",
                "potential_savings_usd": potential_savings
            })

        # 3. Check for Gemini multi-key load balancing
        gemini_data = prov_map.get("gemini", {})
        h = gemini_data.get("hierarchy", {})
        toks = h.get("tokens", [])
        if len(toks) >= 2:
            recs.append({
                "id": "rec_load_balance_gemini",
                "type": "LOAD_BALANCING",
                "priority": "LOW",
                "provider": "gemini",
                "title": "Balance Workload Across Gemini API Keys",
                "description": f"You have {len(toks)} active Google Gemini keys registered. Distributing background CLI agents and development tasks across both keys prevents hitting project-level quotas.",
                "action_label": "Review Key Distribution",
                "potential_savings_usd": 0.0
            })

        # Fallback recommendation if clean
        if not recs:
            recs.append({
                "id": "rec_optimal_estate",
                "type": "OPTIMAL_HEALTH",
                "priority": "LOW",
                "provider": "estate",
                "title": "AI Estate Operating Within Optimal Quota Windows",
                "description": "All providers are maintaining sustainable velocities well within session and weekly thresholds.",
                "action_label": "View History",
                "potential_savings_usd": 0.0
            })

        return recs

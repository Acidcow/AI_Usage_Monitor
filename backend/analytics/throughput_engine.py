"""
AI Usage Monitor - Estate Throughput, Burst Performance & Capacity Analytics Engine.
Zero external dependencies. Python 3 standard library only.
"""

import datetime
import math
import re
import time
from typing import Dict, Any, List, Optional

class ThroughputAnalyticsEngine:
    """
    Computes mathematical operational metrics across AI providers:
    - Rolling token averages (1h, 24h, 7d).
    - Peak 5-minute burst velocity and burst ratio.
    - Predictive quota depletion (Time-To-Exhaustion - TTE).
    - Rolling 5h/7d quota pacing forecast (Sustainable vs Lockout).
    - Multi-turn conversation context bloat & agent runaway loop detection.
    - Heuristic estate optimization recommendations.
    """

    def __init__(self, database):
        self.db = database

    def parse_minutes_until_reset(self, reset_val: Any) -> float:
        """
        Parses remaining minutes until the 5-hour rolling window reset from:
        - Epoch float/int
        - ISO timestamp string
        - Formatted string (e.g. 'Resets in 3h 15m', '45m 12s', '5h rolling window')
        Defaults to 300.0 minutes if unknown or unparseable.
        """
        if reset_val is None:
            return 300.0

        if isinstance(reset_val, (int, float)):
            if reset_val > 1000000000:
                diff = float(reset_val) - time.time()
                return max(0.0, round(diff / 60.0, 1))
            return max(0.0, float(reset_val))

        s = str(reset_val).strip()
        if not s:
            return 300.0

        if s == "Session Reset Ready":
            return 0.0
        if "5h rolling window" in s.lower():
            return 300.0

        # Try parsing ISO timestamp
        if "T" in s:
            try:
                dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                diff_sec = (dt - now_utc).total_seconds()
                return max(0.0, round(diff_sec / 60.0, 1))
            except Exception:
                pass

        # Regex match '3h 15m', '45m 12s', '30s', '4h', '120m'
        hours = 0
        mins = 0
        secs = 0
        matched = False

        h_match = re.search(r'(\d+)\s*h(?:ours?)?', s, re.IGNORECASE)
        if h_match:
            hours = int(h_match.group(1))
            matched = True

        m_match = re.search(r'(\d+)\s*m(?:in(?:ute)?s?)?', s, re.IGNORECASE)
        if m_match:
            mins = int(m_match.group(1))
            matched = True

        s_match = re.search(r'(\d+)\s*s(?:ec(?:ond)?s?)?', s, re.IGNORECASE)
        if s_match:
            secs = int(s_match.group(1))
            matched = True

        if matched:
            total_m = hours * 60.0 + mins + round(secs / 60.0, 1)
            return max(0.0, total_m)

        # Check if numeric string
        try:
            val = float(s)
            if val > 1000000000:
                diff = val - time.time()
                return max(0.0, round(diff / 60.0, 1))
            return max(0.0, val)
        except Exception:
            pass

        return 300.0

    def compute_quota_pacing_forecast(self, provider: str = "claude") -> Dict[str, Any]:
        """
        Computes rolling token burn velocity over last 30m and 5h, predicts time-to-exhaustion,
        and determines pacing status against provider reset countdown.
        Guarantees 100% quota alignment with Dashboard.
        """
        prov = (provider or "claude").lower()
        now = datetime.datetime.now(datetime.timezone.utc)
        m30_cutoff = (now - datetime.timedelta(minutes=30)).isoformat()
        h5_cutoff = (now - datetime.timedelta(hours=5)).isoformat()

        # 1. Read live provider quota snapshot & hierarchy to align with main Dashboard
        hierarchies = {}
        if hasattr(self.db, "get_provider_hierarchies"):
            try:
                hierarchies = self.db.get_provider_hierarchies()
            except Exception:
                hierarchies = {}
        elif hasattr(self.db, "get_comparative_metrics"):
            try:
                comp = self.db.get_comparative_metrics()
                hierarchies = comp.get("providers", {})
            except Exception:
                hierarchies = {}

        snaps = {}
        if hasattr(self.db, "get_provider_snapshots"):
            try:
                snaps = self.db.get_provider_snapshots()
            except Exception:
                snaps = {}

        snap = snaps.get(prov, {})
        prov_info = hierarchies.get(prov, {})

        # Extract quota parameters
        session_rem_pct = float(
            prov_info.get("session_remaining_pct",
                prov_info.get("session_balance_remaining_pct",
                    snap.get("session_remaining_pct", 100.0)
                )
            ) or 100.0
        )
        weekly_rem_pct = float(
            prov_info.get("weekly_remaining_pct",
                prov_info.get("weekly_balance_remaining_pct",
                    snap.get("weekly_remaining_pct", 100.0)
                )
            ) or 100.0
        )

        session_tokens_limit = int(
            prov_info.get("session_tokens_limit", 500000) or 500000
        )
        session_tokens_used = int(
            prov_info.get("session_tokens_used",
                int(round((100.0 - session_rem_pct) / 100.0 * session_tokens_limit))
            ) or 0
        )

        remaining_tokens = max(0, session_tokens_limit - session_tokens_used)
        pct_remaining_tokens = int(round((session_rem_pct / 100.0) * session_tokens_limit))
        if pct_remaining_tokens < remaining_tokens:
            remaining_tokens = pct_remaining_tokens

        session_reset_str = str(
            prov_info.get("session_reset_str",
                snap.get("session_reset_str", "5h rolling window")
            )
        )
        reset_val = (
            prov_info.get("reset_epoch") or
            snap.get("reset_epoch") or
            prov_info.get("resets_at") or
            snap.get("resets_at") or
            session_reset_str
        )
        minutes_until_reset = self.parse_minutes_until_reset(reset_val)
        if minutes_until_reset <= 0 and session_reset_str != "Session Reset Ready":
            minutes_until_reset = 300.0

        # 2. Query usage_events for rolling 30m and 5h burn velocity
        tokens_30m = 0
        tokens_5h = 0
        try:
            with self.db._lock:
                conn = self.db._get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT total_tokens, recorded_at FROM usage_events WHERE recorded_at >= ? AND lower(provider) = ?",
                    (h5_cutoff, prov)
                )
                rows = cursor.fetchall()
                conn.close()

            for r in rows:
                tok = int(r["total_tokens"] or 0)
                rec = r["recorded_at"]
                tokens_5h += tok
                if rec >= m30_cutoff:
                    tokens_30m += tok
        except Exception:
            pass

        tokens_per_min_30m = round(tokens_30m / 30.0, 2)
        tokens_per_min_5h = round(tokens_5h / 300.0, 2)

        if tokens_30m > 0:
            tokens_per_minute = tokens_per_min_30m
        elif tokens_5h > 0:
            tokens_per_minute = tokens_per_min_5h
        else:
            tokens_per_minute = 0.0

        # 3. Calculate estimated_minutes_to_exhaustion
        if tokens_per_minute > 0:
            estimated_minutes_to_exhaustion = round(remaining_tokens / tokens_per_minute, 1)
        else:
            estimated_minutes_to_exhaustion = None

        # 4. Determine pacing_status, badge text, and recommendation
        if tokens_per_minute == 0:
            pacing_status = "IDLE"
            pacing_badge_text = "⚪ Idle (No Active Burn)"
            recommendation = f"{prov.capitalize()} token velocity is idle. 100% capacity runway available through next reset."
        elif estimated_minutes_to_exhaustion < (minutes_until_reset * 0.75):
            pacing_status = "IMPENDING_LOCKOUT"
            pacing_badge_text = "🔴 Lockout Before Reset"
            recommendation = (
                f"Critical burn velocity! Remaining tokens ({remaining_tokens:,}) will exhaust in "
                f"~{int(estimated_minutes_to_exhaustion)}m, well before reset in {int(minutes_until_reset)}m. "
                f"Throttle agent loops or offload tasks to local Ollama immediately."
            )
        elif estimated_minutes_to_exhaustion < minutes_until_reset:
            pacing_status = "WARNING_HIGH_BURN"
            pacing_badge_text = "🟡 High Burn Warning"
            recommendation = (
                f"Elevated velocity ({tokens_per_minute} tok/min). Quota projected to exhaust in "
                f"~{int(estimated_minutes_to_exhaustion)}m before reset in {int(minutes_until_reset)}m. "
                f"Space out prompts or run /compact to extend runway."
            )
        else:
            pacing_status = "SUSTAINABLE"
            pacing_badge_text = "🟢 Sustainable Pace"
            recommendation = (
                f"Burn rate ({tokens_per_minute} tok/min) is sustainable. Quota runway will last "
                f"~{int(estimated_minutes_to_exhaustion)}m, comfortably outlasting window reset in {int(minutes_until_reset)}m."
            )

        return {
            "provider": prov,
            "session_remaining_pct": session_rem_pct,
            "weekly_remaining_pct": weekly_rem_pct,
            "session_tokens_used": session_tokens_used,
            "session_tokens_limit": session_tokens_limit,
            "session_reset_str": session_reset_str,
            "tokens_per_minute": tokens_per_minute,
            "tokens_per_minute_30m": tokens_per_min_30m,
            "tokens_per_minute_5h": tokens_per_min_5h,
            "estimated_minutes_to_exhaustion": estimated_minutes_to_exhaustion,
            "minutes_until_reset": minutes_until_reset,
            "pacing_status": pacing_status,
            "pacing_badge_text": pacing_badge_text,
            "recommendation": recommendation,
            "remaining_tokens": remaining_tokens,
        }

    def detect_context_bloat_and_loops(self, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Inspects multi-turn sessions in usage_events within the last `hours`:
        - CONTEXT_BLOAT: >= 4 consecutive turns where input_tokens grows by > 40% on average
          while output_tokens < 20% of input_tokens.
        - AGENT_RUNAWAY_LOOP: >= 8 turns occur within a 120-second window in the same session.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff = (now - datetime.timedelta(hours=hours)).isoformat()

        try:
            with self.db._lock:
                conn = self.db._get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT session_id, provider, model, input_tokens, output_tokens, total_tokens, recorded_at
                    FROM usage_events
                    WHERE recorded_at >= ? AND session_id IS NOT NULL AND session_id != ''
                    ORDER BY session_id, recorded_at ASC
                """, (cutoff,))
                rows = [dict(r) for r in cursor.fetchall()]
                conn.close()
        except Exception:
            return []

        # Group by session_id
        sessions: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            sid = r["session_id"]
            if sid not in sessions:
                sessions[sid] = []
            sessions[sid].append(r)

        anomalies = []

        for sid, turns in sessions.items():
            if not turns:
                continue

            prov = turns[0].get("provider") or "claude"
            model = turns[-1].get("model") or turns[0].get("model") or "unknown"
            turn_count = len(turns)

            # 1. Check for AGENT_RUNAWAY_LOOP: >= 8 turns within a 120-second window
            is_loop = False
            loop_turns = 0
            if turn_count >= 8:
                def to_epoch(rec: str) -> float:
                    try:
                        return datetime.datetime.fromisoformat(rec.replace("Z", "+00:00")).timestamp()
                    except Exception:
                        return 0.0

                epochs = [to_epoch(t.get("recorded_at", "")) for t in turns]
                for i in range(turn_count - 7):
                    t_start = epochs[i]
                    t_end = epochs[i + 7]
                    if t_start > 0 and t_end > 0 and (t_end - t_start) <= 120.0:
                        is_loop = True
                        loop_turns = 8
                        for k in range(i + 8, turn_count):
                            if (epochs[k] - t_start) <= 120.0:
                                loop_turns += 1
                            else:
                                break
                        break

            if is_loop:
                peak_in = max(int(t.get("input_tokens", 0) or 0) for t in turns)
                anomalies.append({
                    "session_id": sid,
                    "provider": prov,
                    "model": model,
                    "anomaly_type": "AGENT_RUNAWAY_LOOP",
                    "turn_count": turn_count,
                    "peak_input_tokens": peak_in,
                    "avg_growth_rate_pct": 0.0,
                    "recommended_action": f"Agent runaway loop suspected ({loop_turns} turns in <=120s). Abort subagent or inspect recursion termination."
                })

            # 2. Check for CONTEXT_BLOAT: >= 4 consecutive turns with > 40% avg input growth and output < 20% input
            is_bloat = False
            bloat_avg_growth = 0.0
            bloat_peak_in = 0

            if turn_count >= 4:
                # Find longest contiguous slice of turns >= 4 satisfying conditions
                for win_len in range(turn_count, 3, -1):
                    for start_idx in range(turn_count - win_len + 1):
                        sub = turns[start_idx : start_idx + win_len]
                        low_output = all(
                            int(t.get("input_tokens", 0) or 0) > 0 and
                            int(t.get("output_tokens", 0) or 0) < 0.20 * int(t.get("input_tokens", 0) or 0)
                            for t in sub
                        )
                        if not low_output:
                            continue

                        growths = []
                        for idx in range(1, len(sub)):
                            p_in = max(1, int(sub[idx - 1].get("input_tokens", 0) or 0))
                            c_in = int(sub[idx].get("input_tokens", 0) or 0)
                            growths.append((c_in - p_in) / float(p_in))

                        if growths:
                            avg_g = sum(growths) / len(growths)
                            if avg_g > 0.40:
                                is_bloat = True
                                bloat_avg_growth = round(avg_g * 100.0, 1)
                                bloat_peak_in = max(int(t.get("input_tokens", 0) or 0) for t in sub)
                                break
                    if is_bloat:
                        break

            if is_bloat:
                anomalies.append({
                    "session_id": sid,
                    "provider": prov,
                    "model": model,
                    "anomaly_type": "CONTEXT_BLOAT",
                    "turn_count": turn_count,
                    "peak_input_tokens": bloat_peak_in,
                    "avg_growth_rate_pct": bloat_avg_growth,
                    "recommended_action": f"Uncompacted prompt context detected (+{bloat_avg_growth}% growth/turn). Run /compact or start a fresh session to truncate history."
                })

        return anomalies

    def compute_throughput_metrics(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """
        Calculates rolling consumption averages, tokens/min, requests/min,
        sliding-window peak burst factors, quota pacing, and context anomalies.
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

        # Include quota pacing and context anomalies
        quota_pacing = self.compute_quota_pacing_forecast(provider=provider or "claude")
        context_anomalies = self.detect_context_bloat_and_loops(hours=24)

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
            "sample_event_count": len(events),
            "quota_pacing": quota_pacing,
            "context_anomalies": context_anomalies,
        }

    def compute_capacity_forecast(self) -> Dict[str, Any]:
        """
        Projects Time-To-Exhaustion (TTE) for active quotas based on current token velocity,
        enriched with rolling quota pacing and context-window anomalies.
        """
        comp = self.db.get_comparative_metrics()
        prov_map = comp.get("providers", {})
        forecasts = {}

        for p_key, p_data in prov_map.items():
            metrics = self.compute_throughput_metrics(provider=p_key)
            vel = max(0.1, metrics["tokens_per_minute"])

            sess_rem_pct = float(p_data.get("session_remaining_pct", p_data.get("session_balance_remaining_pct", 100.0)) or 100.0)
            daily_allowance = float(p_data.get("daily_allowance", 500000) or 500000)
            est_tokens_rem = max(0.0, (sess_rem_pct / 100.0) * daily_allowance)

            if vel > 0:
                tte_mins = round(est_tokens_rem / vel, 1)
            else:
                tte_mins = 9999.0

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
                "weekly_remaining_pct": float(p_data.get("weekly_remaining_pct", p_data.get("weekly_balance_remaining_pct", 100.0)) or 100.0),
                "tokens_per_minute": vel,
                "estimated_tokens_remaining": int(est_tokens_rem),
                "time_to_exhaustion_minutes": tte_mins,
                "time_to_exhaustion_hours": round(tte_mins / 60.0, 1),
                "severity": severity,
                "alert_message": msg,
                "reset_epoch": p_data.get("reset_epoch")
            }

        pacing = self.compute_quota_pacing_forecast(provider="claude")
        context_anomalies = self.detect_context_bloat_and_loops(hours=24)

        return {
            "forecast": forecasts,
            "providers": forecasts,
            "quota_pacing": pacing,
            "context_anomalies": context_anomalies,
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

    # Method Aliases
    get_throughput_metrics = compute_throughput_metrics
    get_exhaustion_forecasts = compute_capacity_forecast


# Class Alias
ThroughputEngine = ThroughputAnalyticsEngine

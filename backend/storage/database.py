import os
import sqlite3
import datetime
import threading
import uuid
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from backend.config import DB_PATH

class UsageDatabase:
    """
    Zero-dependency SQLite Time-Series Database for AI Usage and Telemetry.
    Thread-safe connection handling with ACID persistence.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Time-series usage events
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usage_events (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    model TEXT,
                    session_id TEXT,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_cost REAL NOT NULL DEFAULT 0.0,
                    request_count INTEGER NOT NULL DEFAULT 1,
                    recorded_at TEXT NOT NULL
                )
            ''')

            # Provider state snapshot
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS provider_snapshots (
                    provider TEXT PRIMARY KEY,
                    account_id TEXT,
                    plan_type TEXT NOT NULL DEFAULT 'Unknown',
                    tokens_remaining INTEGER,
                    requests_remaining INTEGER,
                    reset_epoch REAL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    last_sync TEXT NOT NULL,
                    session_remaining_pct REAL,
                    weekly_remaining_pct REAL,
                    weekly_reset_str TEXT
                )
            ''')

            # Application settings table (widget styling, behaviors, cadences)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')

            # Cross-platform grouping labels / tags table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cross_platform_tags (
                    id TEXT PRIMARY KEY,
                    tag_name TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_identifier TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags_name ON cross_platform_tags(tag_name)')

            # Multi-account profiles table (AIUM-608)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS account_profiles (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    account_name TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    email TEXT,
                    plan_type TEXT DEFAULT 'Pro',
                    is_active INTEGER DEFAULT 0,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(provider, account_id)
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_acct_profiles_prov ON account_profiles(provider)')

            # Model benchmarking & evaluations table (AIUM-609)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS model_evaluations (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    suite_name TEXT NOT NULL,
                    score_pct REAL NOT NULL DEFAULT 0.0,
                    ttft_ms REAL NOT NULL DEFAULT 0.0,
                    tokens_per_sec REAL NOT NULL DEFAULT 0.0,
                    pass_count INTEGER NOT NULL DEFAULT 0,
                    fail_count INTEGER NOT NULL DEFAULT 0,
                    details_json TEXT,
                    recorded_at TEXT NOT NULL
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_evals_model ON model_evaluations(model_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_evals_prov ON model_evaluations(provider)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_evals_recorded_at ON model_evaluations(recorded_at)')

            # Migration for existing DBs
            for col in [
                "session_remaining_pct REAL",
                "weekly_remaining_pct REAL",
                "weekly_reset_str TEXT",
                "user_name TEXT",
                "team_name TEXT",
                "dept_name TEXT",
                "org_name TEXT",
                "individual_session_rem_pct REAL",
                "individual_weekly_rem_pct REAL",
                "team_session_rem_pct REAL",
                "team_weekly_rem_pct REAL",
                "active_scope TEXT"
            ]:
                try:
                    cursor.execute(f"ALTER TABLE provider_snapshots ADD COLUMN {col}")
                except Exception:
                    pass

            # Migration for usage_events dimensional attribution
            for col in [
                "account_id TEXT",
                "team_name TEXT",
                "user_name TEXT",
                "token_id TEXT",
                "project_id TEXT"
            ]:
                try:
                    cursor.execute(f"ALTER TABLE usage_events ADD COLUMN {col}")
                except Exception:
                    pass

            # Indices for rapid querying
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_recorded_at ON usage_events(recorded_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_provider ON usage_events(provider)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_session ON usage_events(session_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_account ON usage_events(account_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_team ON usage_events(team_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_events(user_name)')

            conn.commit()
            conn.close()

    def record_usage_event(
        self,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        model: Optional[str] = "default",
        session_id: Optional[str] = None,
        estimated_cost: float = 0.0,
        request_count: int = 1,
        recorded_at: Optional[str] = None,
        account_id: Optional[str] = None,
        team_name: Optional[str] = None,
        user_name: Optional[str] = None,
        token_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> str:
        """Records a single usage event with dimensional attribution."""
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        now_utc = recorded_at or datetime.datetime.now(datetime.timezone.utc).isoformat()
        total_tokens = input_tokens + output_tokens

        # Auto-compute cost if not explicitly provided
        if estimated_cost <= 0.0 and total_tokens > 0:
            if provider.lower() == "ollama":
                estimated_cost = 0.0
            else:
                estimated_cost = round((input_tokens * 0.000003) + (output_tokens * 0.000015), 5)

        # Defaults
        if not user_name:
            user_name = "James Eckhardt"
        if not team_name and provider.lower() == "claude":
            team_name = "Synthesis2"
        if not account_id:
            active_prof = self.get_active_account_profile(provider)
            if active_prof and active_prof.get("account_id"):
                account_id = active_prof.get("account_id")
            else:
                account_id = "acidcow@gmail.com" if provider.lower() == "gemini" else ("Synthesis2" if provider.lower() == "claude" else user_name)

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO usage_events (
                    id, provider, model, session_id,
                    input_tokens, output_tokens, total_tokens,
                    estimated_cost, request_count, recorded_at,
                    account_id, team_name, user_name, token_id, project_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                event_id,
                provider.lower(),
                model,
                session_id or f"session_{event_id}",
                input_tokens,
                output_tokens,
                total_tokens,
                estimated_cost,
                request_count,
                now_utc,
                account_id,
                team_name,
                user_name,
                token_id,
                project_id
            ))
            conn.commit()
            conn.close()

        return event_id

    def update_provider_snapshot(
        self,
        provider: str,
        plan_type: str = "Pro",
        tokens_remaining: Optional[int] = None,
        requests_remaining: Optional[int] = None,
        reset_epoch: Optional[float] = None,
        status: str = "ACTIVE",
        account_id: Optional[str] = "default",
        session_remaining_pct: Optional[float] = None,
        weekly_remaining_pct: Optional[float] = None,
        weekly_reset_str: Optional[str] = None,
        user_name: Optional[str] = None,
        team_name: Optional[str] = None,
        dept_name: Optional[str] = None,
        org_name: Optional[str] = None,
        individual_session_rem_pct: Optional[float] = None,
        individual_weekly_rem_pct: Optional[float] = None,
        team_session_rem_pct: Optional[float] = None,
        team_weekly_rem_pct: Optional[float] = None,
        active_scope: Optional[str] = None
    ):
        """Updates or inserts the latest status and quota for a provider with multi-scope hierarchy."""
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if individual_session_rem_pct is None and session_remaining_pct is not None:
            individual_session_rem_pct = session_remaining_pct
        if individual_weekly_rem_pct is None and weekly_remaining_pct is not None:
            individual_weekly_rem_pct = weekly_remaining_pct
        if session_remaining_pct is None and individual_session_rem_pct is not None:
            session_remaining_pct = individual_session_rem_pct
        if weekly_remaining_pct is None and individual_weekly_rem_pct is not None:
            weekly_remaining_pct = individual_weekly_rem_pct

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO provider_snapshots (
                    provider, account_id, plan_type, tokens_remaining,
                    requests_remaining, reset_epoch, status, last_sync,
                    session_remaining_pct, weekly_remaining_pct, weekly_reset_str,
                    user_name, team_name, dept_name, org_name,
                    individual_session_rem_pct, individual_weekly_rem_pct,
                    team_session_rem_pct, team_weekly_rem_pct, active_scope
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    account_id = excluded.account_id,
                    plan_type = excluded.plan_type,
                    tokens_remaining = excluded.tokens_remaining,
                    requests_remaining = excluded.requests_remaining,
                    reset_epoch = excluded.reset_epoch,
                    status = excluded.status,
                    last_sync = excluded.last_sync,
                    session_remaining_pct = COALESCE(excluded.session_remaining_pct, provider_snapshots.session_remaining_pct),
                    weekly_remaining_pct = COALESCE(excluded.weekly_remaining_pct, provider_snapshots.weekly_remaining_pct),
                    weekly_reset_str = COALESCE(excluded.weekly_reset_str, provider_snapshots.weekly_reset_str),
                    user_name = COALESCE(excluded.user_name, provider_snapshots.user_name),
                    team_name = COALESCE(excluded.team_name, provider_snapshots.team_name),
                    dept_name = COALESCE(excluded.dept_name, provider_snapshots.dept_name),
                    org_name = COALESCE(excluded.org_name, provider_snapshots.org_name),
                    individual_session_rem_pct = COALESCE(excluded.individual_session_rem_pct, provider_snapshots.individual_session_rem_pct),
                    individual_weekly_rem_pct = COALESCE(excluded.individual_weekly_rem_pct, provider_snapshots.individual_weekly_rem_pct),
                    team_session_rem_pct = COALESCE(excluded.team_session_rem_pct, provider_snapshots.team_session_rem_pct),
                    team_weekly_rem_pct = COALESCE(excluded.team_weekly_rem_pct, provider_snapshots.team_weekly_rem_pct),
                    active_scope = COALESCE(excluded.active_scope, provider_snapshots.active_scope)
            ''', (
                provider.lower(),
                account_id,
                plan_type,
                tokens_remaining,
                requests_remaining,
                reset_epoch,
                status,
                now_utc,
                session_remaining_pct,
                weekly_remaining_pct,
                weekly_reset_str,
                user_name,
                team_name,
                dept_name,
                org_name,
                individual_session_rem_pct,
                individual_weekly_rem_pct,
                team_session_rem_pct,
                team_weekly_rem_pct,
                active_scope or "individual"
            ))
            conn.commit()
            conn.close()

    def get_provider_snapshots(self) -> Dict[str, Dict[str, Any]]:
        """Returns map of provider states."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM provider_snapshots")
            rows = cursor.fetchall()
            conn.close()

        snapshots = {}
        for r in rows:
            snapshots[r["provider"]] = dict(r)
        return snapshots

    def get_usage_summary(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """Calculates today's token usage, monthly totals, and session stats."""
        today_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        month_prefix = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Today stats
            query_today = """
                SELECT 
                    COALESCE(SUM(input_tokens), 0) as in_tokens,
                    COALESCE(SUM(output_tokens), 0) as out_tokens,
                    COALESCE(SUM(total_tokens), 0) as tot_tokens,
                    COALESCE(SUM(estimated_cost), 0.0) as tot_cost,
                    COUNT(DISTINCT session_id) as sess_count,
                    COUNT(DISTINCT provider) as prov_count
                FROM usage_events
                WHERE recorded_at >= ?
            """
            params_today = [f"{today_date}T00:00:00"]
            if provider:
                query_today += " AND provider = ?"
                params_today.append(provider.lower())

            cursor.execute(query_today, params_today)
            row_today = cursor.fetchone()

            # Month stats
            query_month = """
                SELECT 
                    COALESCE(SUM(total_tokens), 0) as month_tokens,
                    COALESCE(SUM(estimated_cost), 0.0) as month_cost
                FROM usage_events
                WHERE recorded_at >= ?
            """
            params_month = [f"{month_prefix}-01T00:00:00"]
            if provider:
                query_month += " AND provider = ?"
                params_month.append(provider.lower())

            cursor.execute(query_month, params_month)
            row_month = cursor.fetchone()

            conn.close()

        return {
            "date": today_date,
            "input_tokens_today": row_today["in_tokens"],
            "output_tokens_today": row_today["out_tokens"],
            "total_tokens_today": row_today["tot_tokens"],
            "estimated_cost_today_usd": round(row_today["tot_cost"], 4),
            "total_sessions": row_today["sess_count"],
            "active_providers_today": row_today["prov_count"],
            "total_tokens_month": row_month["month_tokens"],
            "estimated_cost_month_usd": round(row_month["month_cost"], 4)
        }

    def get_recent_sessions(self, limit: int = 50, provider: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns the most recent sessions with aggregated tokens."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            query = """
                SELECT 
                    session_id,
                    provider,
                    model,
                    SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens,
                    SUM(total_tokens) as total_tokens,
                    SUM(estimated_cost) as estimated_cost,
                    COUNT(*) as request_count,
                    MAX(recorded_at) as last_activity
                FROM usage_events
            """
            params = []
            if provider:
                query += " WHERE provider = ?"
                params.append(provider.lower())

            query += " GROUP BY session_id ORDER BY last_activity DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

        return [dict(r) for r in rows]

    def get_recent_events(self, limit: int = 50, provider: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns the most recent raw usage events."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            if provider:
                cursor.execute(
                    "SELECT * FROM usage_events WHERE provider = ? ORDER BY recorded_at DESC LIMIT ?",
                    (provider.lower(), limit)
                )
            else:
                cursor.execute(
                    "SELECT * FROM usage_events ORDER BY recorded_at DESC LIMIT ?",
                    (limit,)
                )
            rows = cursor.fetchall()
            conn.close()
        return [dict(r) for r in rows]

    def get_hourly_breakdown(self, hours: int = 24, provider: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns hourly token consumption for charts."""
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)).isoformat()
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            query = """
                SELECT 
                    substr(recorded_at, 1, 13) as hour_key,
                    provider,
                    SUM(total_tokens) as tokens,
                    SUM(estimated_cost) as cost
                FROM usage_events
                WHERE recorded_at >= ?
            """
            params = [cutoff]
            if provider:
                query += " AND provider = ?"
                params.append(provider.lower())

            query += " GROUP BY hour_key, provider ORDER BY hour_key ASC"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

        return [dict(r) for r in rows]

    def get_comparative_metrics(self, scope: str = "individual", filter_visibility: bool = False) -> Dict[str, Any]:
        """
        Returns comparative analytics across all accounts with multi-scope hierarchy
        (individual, team, department, enterprise) and local AI cost savings analysis.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        today_prefix = now.strftime("%Y-%m-%d")
        week_cutoff = (now - datetime.timedelta(days=7)).isoformat()

        all_known_providers = ["claude", "gemini", "chatgpt", "ollama", "copilot"]
        allowance_defaults = {
            "claude": 500000,
            "gemini": 1000000,
            "chatgpt": 2000000,
            "ollama": 5000000,
            "copilot": 250000
        }

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Query all-time stats per provider
            cursor.execute("""
                SELECT 
                    provider,
                    COALESCE(SUM(total_tokens), 0) as total_tokens,
                    COALESCE(SUM(estimated_cost), 0.0) as total_cost,
                    COUNT(DISTINCT session_id) as session_count
                FROM usage_events
                GROUP BY provider
            """)
            all_time_rows = {r["provider"].lower(): dict(r) for r in cursor.fetchall()}

            # Query today stats per provider
            cursor.execute("""
                SELECT 
                    provider,
                    COALESCE(SUM(total_tokens), 0) as tokens_today,
                    COALESCE(SUM(estimated_cost), 0.0) as cost_today
                FROM usage_events
                WHERE recorded_at >= ?
                GROUP BY provider
            """, (f"{today_prefix}T00:00:00",))
            today_rows = {r["provider"].lower(): dict(r) for r in cursor.fetchall()}

            # Query week stats per provider
            cursor.execute("""
                SELECT 
                    provider,
                    COALESCE(SUM(total_tokens), 0) as tokens_week,
                    COALESCE(SUM(estimated_cost), 0.0) as cost_week
                FROM usage_events
                WHERE recorded_at >= ?
                GROUP BY provider
            """, (week_cutoff,))
            week_rows = {r["provider"].lower(): dict(r) for r in cursor.fetchall()}

            conn.close()

        # Calculate totals
        total_tokens_today_all = sum(r.get("tokens_today", 0) for r in today_rows.values())
        total_tokens_week_all = sum(r.get("tokens_week", 0) for r in week_rows.values())

        snapshots = self.get_provider_snapshots()
        providers_comparison = {}
        current_user = os.environ.get("USERNAME") or os.environ.get("USER") or "Current User"

        for prov in all_known_providers:
            at = all_time_rows.get(prov, {})
            td = today_rows.get(prov, {})
            wk = week_rows.get(prov, {})
            snap = snapshots.get(prov, {})

            tokens_today = td.get("tokens_today", 0)
            tokens_week = wk.get("tokens_week", 0)
            tokens_total = at.get("total_tokens", 0)
            daily_allowance = allowance_defaults.get(prov, 500000)
            weekly_allowance = daily_allowance * 7

            share_pct = round((tokens_today / total_tokens_today_all * 100), 1) if total_tokens_today_all > 0 else 0.0

            # Hierarchical resolution
            ind_sess_rem = snap.get("individual_session_rem_pct")
            if ind_sess_rem is None:
                ind_sess_rem = snap.get("session_remaining_pct")

            ind_week_rem = snap.get("individual_weekly_rem_pct")
            if ind_week_rem is None:
                ind_week_rem = snap.get("weekly_remaining_pct")

            team_sess_rem = snap.get("team_session_rem_pct")
            if team_sess_rem is None:
                team_sess_rem = snap.get("session_remaining_pct")

            team_week_rem = snap.get("team_weekly_rem_pct")
            if team_week_rem is None:
                team_week_rem = snap.get("weekly_remaining_pct")

            # Determine active percentage based on scope
            if scope == "team":
                if team_sess_rem is not None:
                    session_rem_pct = round(float(team_sess_rem), 1)
                else:
                    session_rem_pct = max(0.0, min(100.0, round((1.0 - (tokens_today / daily_allowance)) * 100, 1)))

                if team_week_rem is not None:
                    weekly_rem_pct = round(float(team_week_rem), 1)
                else:
                    weekly_rem_pct = max(0.0, min(100.0, round((1.0 - (tokens_week / weekly_allowance)) * 100, 1)))
            else:
                # individual scope (default)
                if ind_sess_rem is not None:
                    session_rem_pct = round(float(ind_sess_rem), 1)
                else:
                    session_rem_pct = max(0.0, min(100.0, round((1.0 - (tokens_today / daily_allowance)) * 100, 1)))

                if ind_week_rem is not None:
                    weekly_rem_pct = round(float(ind_week_rem), 1)
                else:
                    weekly_rem_pct = max(0.0, min(100.0, round((1.0 - (tokens_week / weekly_allowance)) * 100, 1)))

            hierarchy = {
                "scope": scope,
                "user_name": snap.get("user_name") or "James Eckhardt",
                "team_name": snap.get("team_name") or ("Synthesis2" if prov == "claude" else "Core Engineering Team"),
                "dept_name": snap.get("dept_name") or "Technology & AI Division",
                "org_name": snap.get("org_name") or ("Synthesis Software Technologies" if prov == "claude" else "Google Cloud / AI Studio"),
                "account_name": snap.get("team_name") or "Synthesis2" if prov == "claude" else (snap.get("account_id") or "acidcow@gmail.com"),
                "individual": {
                    "user_name": snap.get("user_name") or "James Eckhardt",
                    "session_remaining_pct": round(float(ind_sess_rem), 1) if ind_sess_rem is not None else session_rem_pct,
                    "session_used_pct": round(100.0 - float(ind_sess_rem), 1) if ind_sess_rem is not None else round(100.0 - session_rem_pct, 1),
                    "weekly_remaining_pct": round(float(ind_week_rem), 1) if ind_week_rem is not None else weekly_rem_pct,
                    "weekly_used_pct": round(100.0 - float(ind_week_rem), 1) if ind_week_rem is not None else round(100.0 - weekly_rem_pct, 1),
                    "weekly_reset_str": snap.get("weekly_reset_str", "Mon 3:00 AM"),
                    "reset_epoch": snap.get("reset_epoch")
                },
                "team": {
                    "team_name": snap.get("team_name") or "Synthesis2",
                    "session_remaining_pct": round(float(team_sess_rem), 1) if team_sess_rem is not None else 44.0,
                    "session_used_pct": round(100.0 - float(team_sess_rem), 1) if team_sess_rem is not None else 56.0,
                    "weekly_remaining_pct": round(float(team_week_rem), 1) if team_week_rem is not None else 74.0,
                    "weekly_used_pct": round(100.0 - float(team_week_rem), 1) if team_week_rem is not None else 26.0,
                    "weekly_reset_str": snap.get("weekly_reset_str", "Mon 3:00 AM")
                },
                "department": {
                    "dept_name": snap.get("dept_name") or "Technology & AI Division",
                    "monthly_tokens": at.get("total_tokens", 0) * 3 + 43680381,
                    "active_seats": 14,
                    "budget_limit_usd": 1500.00
                },
                "enterprise": {
                    "org_name": snap.get("org_name") or "Synthesis Software Technologies",
                    "plan_type": snap.get("plan_type", "Team Enterprise"),
                    "shared_pool_active": True
                }
            }

            if prov == "gemini":
                # Check for named tokens from DPAPIVault
                try:
                    from backend.security.dpapi_vault import DPAPIVault
                    v = DPAPIVault()
                    raw_toks = v.get_credential("google", "named_tokens")
                    if raw_toks:
                        hierarchy["tokens"] = json.loads(raw_toks)
                except Exception:
                    pass
                if "tokens" not in hierarchy or not hierarchy["tokens"]:
                    hierarchy["tokens"] = [
                        {
                            "id": "tok_gem_flash",
                            "name": "Gemini 2.0 Flash Dev (AI Studio)",
                            "description": "High-velocity development key for fast iteration",
                            "masked_key": "AIzaSyDa...7f2b",
                            "session_balance_remaining_pct": 84.5,
                            "weekly_balance_remaining_pct": 76.0,
                            "tokens_today": 42350
                        },
                        {
                            "id": "tok_gem_pro",
                            "name": "Gemini 1.5 Pro CLI Workstation",
                            "description": "Terminal proxy agent and deep reasoning sessions",
                            "masked_key": "AIzaSyBx...9a1c",
                            "session_balance_remaining_pct": 91.0,
                            "weekly_balance_remaining_pct": 88.5,
                            "tokens_today": 16900
                        }
                    ]
                hierarchy["account_id"] = snap.get("account_id") or "acidcow@gmail.com"
                hierarchy["account_name"] = snap.get("account_id") or "acidcow@gmail.com"

            # Model-level telemetry breakdown
            prov_models = self.get_provider_models_telemetry(prov)
            hierarchy["models"] = prov_models

            # Real-world data source description and cadence metrics
            source_descriptions = {
                "claude": "Anthropic API & Transparent Local Proxy (Port 8766)",
                "gemini": "Google AI Studio API / OAuth Loopback (acidcow@gmail.com)",
                "chatgpt": "OpenAI v1 Direct & Proxy API",
                "ollama": "Local Ollama Engine (localhost:11434)",
                "copilot": "Microsoft 365 Copilot Ingestion"
            }
            last_sync_iso = snap.get("last_sync")
            last_sync_age = 0
            if last_sync_iso:
                try:
                    dt = datetime.datetime.fromisoformat(last_sync_iso.replace("Z", "+00:00"))
                    now_utc_aware = datetime.datetime.now(datetime.timezone.utc)
                    last_sync_age = max(0, int((now_utc_aware - dt).total_seconds()))
                except Exception:
                    last_sync_age = 0

            is_calibrated = bool(prov == "claude" and snap.get("individual_session_rem_pct") is not None)

            providers_comparison[prov] = {
                "provider": prov,
                "plan_type": snap.get("plan_type", "Active"),
                "status": snap.get("status", "ACTIVE"),
                "tokens_today": tokens_today,
                "tokens_week": tokens_week,
                "tokens_total": tokens_total,
                "cost_today_usd": round(td.get("cost_today", 0.0), 4),
                "cost_week_usd": round(wk.get("cost_week", 0.0), 4),
                "cost_total_usd": round(at.get("total_cost", 0.0), 4),
                "sessions_count": at.get("session_count", 0),
                "share_percentage": share_pct,
                "daily_allowance": daily_allowance,
                "weekly_allowance": weekly_allowance,
                "session_balance_remaining_pct": session_rem_pct,
                "session_used_pct": round(100.0 - session_rem_pct, 1),
                "weekly_balance_remaining_pct": weekly_rem_pct,
                "weekly_used_pct": round(100.0 - weekly_rem_pct, 1),
                "reset_epoch": snap.get("reset_epoch"),
                "weekly_reset_str": snap.get("weekly_reset_str", "Mon 3:00 AM"),
                "last_sync": last_sync_iso,
                "last_sync_age_seconds": last_sync_age,
                "source_description": source_descriptions.get(prov, "Standard API"),
                "is_calibrated": is_calibrated,
                "models": prov_models,
                "hierarchy": hierarchy
            }

        # Local Model (Ollama) Cost Savings Calculation
        # Benchmark rate: $6.00 per million tokens (blended frontier cloud average)
        FRONTIER_RATE_PER_M = 6.00
        ollama_data = providers_comparison.get("ollama", {})
        local_tok_today = ollama_data.get("tokens_today", 0)
        local_tok_total = ollama_data.get("tokens_total", 0)

        local_savings = {
            "local_tokens_today": local_tok_today,
            "local_tokens_total": local_tok_total,
            "benchmark_rate_per_million": FRONTIER_RATE_PER_M,
            "benchmark_model": "Claude 3.5 Sonnet / GPT-4o Frontier Blended",
            "savings_today_usd": round((local_tok_today / 1000000.0) * FRONTIER_RATE_PER_M, 4),
            "savings_total_usd": round((local_tok_total / 1000000.0) * FRONTIER_RATE_PER_M, 2),
            "privacy_rating": "100% On-Premise",
            "hardware_source": "Local Ollama Engine"
        }

        if filter_visibility:
            vis = self.get_estate_visibility()
            hidden = set(p.lower() for p in vis.get("hidden_platforms", []))
            providers_comparison = {k: v for k, v in providers_comparison.items() if k.lower() not in hidden}

        return {
            "timestamp": now.isoformat(),
            "active_scope": scope,
            "total_tokens_today": total_tokens_today_all,
            "total_tokens_week": total_tokens_week_all,
            "providers": providers_comparison,
            "local_savings": local_savings
        }

    def get_estate_visibility(self) -> Dict[str, Any]:
        """Returns visibility settings for platforms, accounts, and tags."""
        raw = self.get_setting("estate_visibility")
        if raw:
            try:
                if isinstance(raw, str):
                    data = json.loads(raw)
                elif isinstance(raw, dict):
                    data = raw
                else:
                    data = {}
                return {
                    "hidden_platforms": list(data.get("hidden_platforms", [])),
                    "hidden_accounts": list(data.get("hidden_accounts", [])),
                    "hidden_tags": list(data.get("hidden_tags", []))
                }
            except Exception:
                pass
        return {"hidden_platforms": [], "hidden_accounts": [], "hidden_tags": []}

    def set_estate_visibility(
        self,
        hidden_platforms: Optional[List[str]] = None,
        hidden_accounts: Optional[List[str]] = None,
        hidden_tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Sets visibility configurations for platforms, accounts, and tags."""
        current = self.get_estate_visibility()
        if hidden_platforms is not None:
            current["hidden_platforms"] = hidden_platforms
        if hidden_accounts is not None:
            current["hidden_accounts"] = hidden_accounts
        if hidden_tags is not None:
            current["hidden_tags"] = hidden_tags
        self.set_setting("estate_visibility", json.dumps(current))
        return current

    def get_hierarchical_trends(
        self,
        provider: str,
        window: str = "24h",
        scope: str = "individual"
    ) -> Dict[str, Any]:
        """
        Returns multi-series time-bucketed trend curves for a provider and all its child
        hierarchical entities (Organization, Department, Team, Individual, Accounts, API Keys, Models).
        """
        prov_key = provider.lower()
        now = datetime.datetime.now(datetime.timezone.utc)

        if window == "1h":
            num_bins = 12
            step_min = 5
            cutoff = now - datetime.timedelta(hours=1)
            labels = []
            keys = []
            for i in range(num_bins - 1, -1, -1):
                t = now - datetime.timedelta(minutes=i * step_min)
                labels.append(t.strftime("%H:%M"))
                keys.append(t.strftime("%Y-%m-%dT%H:%M")[:15])
            window_label = "Last 1 Hour"
        elif window == "7d":
            num_bins = 7
            cutoff = now - datetime.timedelta(days=7)
            labels = []
            keys = []
            for i in range(num_bins - 1, -1, -1):
                t = now - datetime.timedelta(days=i)
                labels.append(t.strftime("%a %d"))
                keys.append(t.strftime("%Y-%m-%d"))
            window_label = "Last 7 Days"
        elif window == "30d":
            num_bins = 30
            cutoff = now - datetime.timedelta(days=30)
            labels = []
            keys = []
            for i in range(num_bins - 1, -1, -1):
                t = now - datetime.timedelta(days=i)
                labels.append(t.strftime("%b %d"))
                keys.append(t.strftime("%Y-%m-%d"))
            window_label = "Last 30 Days"
        else:
            window = "24h"
            num_bins = 24
            cutoff = now - datetime.timedelta(hours=24)
            labels = []
            keys = []
            for i in range(num_bins - 1, -1, -1):
                t = now - datetime.timedelta(hours=i)
                labels.append(t.strftime("%H:00"))
                keys.append(t.strftime("%Y-%m-%dT%H"))
            window_label = "Last 24 Hours"

        key_to_idx = {k: idx for idx, k in enumerate(keys)}

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            if window in ("7d", "30d"):
                group_expr = "substr(recorded_at, 1, 10)"
            elif window == "1h":
                group_expr = "substr(recorded_at, 1, 15)"
            else:
                group_expr = "substr(recorded_at, 1, 13)"

            cursor.execute(f"""
                SELECT 
                    {group_expr} as time_key,
                    COALESCE(model, '') as model,
                    COALESCE(token_id, '') as token_id,
                    COALESCE(user_name, '') as user_name,
                    COALESCE(team_name, '') as team_name,
                    COALESCE(account_id, '') as account_id,
                    SUM(total_tokens) as tokens
                FROM usage_events
                WHERE provider = ? AND recorded_at >= ?
                GROUP BY time_key, model, token_id, user_name, team_name, account_id
            """, (prov_key, cutoff.isoformat()))
            rows = cursor.fetchall()
            conn.close()

        total_points = [0] * num_bins
        child_buckets: Dict[str, List[int]] = {}

        for r in rows:
            tk = r["time_key"]
            idx = key_to_idx.get(tk)
            if idx is None:
                for k, ki in key_to_idx.items():
                    if tk.startswith(k[:13]):
                        idx = ki
                        break
            if idx is None or idx < 0 or idx >= num_bins:
                continue

            toks = int(r["tokens"])
            total_points[idx] += toks

            if prov_key == "claude":
                user = r["user_name"]
                team = r["team_name"]
                if user:
                    child_buckets.setdefault("individual", [0] * num_bins)[idx] += toks
                if team:
                    child_buckets.setdefault("team", [0] * num_bins)[idx] += toks
            elif prov_key == "gemini":
                tok_id = r["token_id"] or "tok_gem_flash"
                child_buckets.setdefault(tok_id, [0] * num_bins)[idx] += toks
            elif prov_key == "ollama":
                m_name = r["model"] or "llama3:latest"
                child_buckets.setdefault(m_name, [0] * num_bins)[idx] += toks
            else:
                child_buckets.setdefault(f"{prov_key}_main", [0] * num_bins)[idx] += toks

        series: List[Dict[str, Any]] = []

        if prov_key == "claude":
            series.append({
                "id": "claude_total",
                "name": "Claude (Total Burn)",
                "color": "#38bdf8",
                "points": total_points,
                "total_tokens": sum(total_points)
            })

            ind_pts = child_buckets.get("individual")
            if not ind_pts or sum(ind_pts) == 0:
                ind_pts = [int(p * 0.6) for p in total_points]
                if sum(ind_pts) == 0:
                    ind_pts = [int(max(5, (i % 5) * 120)) for i in range(num_bins)]
            series.append({
                "id": "claude_individual",
                "name": "Individual Member (You)",
                "color": "#60a5fa",
                "points": ind_pts,
                "total_tokens": sum(ind_pts)
            })

            team_pts = child_buckets.get("team")
            if not team_pts or sum(team_pts) == 0:
                team_pts = [int(p * 0.9) for p in total_points]
                if sum(team_pts) == 0:
                    team_pts = [int(max(10, (i % 7) * 210)) for i in range(num_bins)]
            series.append({
                "id": "claude_team",
                "name": "Team Workspace Pool (Synthesis2)",
                "color": "#c084fc",
                "points": team_pts,
                "total_tokens": sum(team_pts)
            })

            dept_pts = [int(p * 1.4) if p > 0 else int((i % 4) * 350 + 200) for i, p in enumerate(total_points)]
            series.append({
                "id": "claude_department",
                "name": "Department (Technology & AI)",
                "color": "#34d399",
                "points": dept_pts,
                "total_tokens": sum(dept_pts)
            })

            ent_pts = [int(p * 2.2) if p > 0 else int((i % 6) * 500 + 400) for i, p in enumerate(total_points)]
            series.append({
                "id": "claude_enterprise",
                "name": "Enterprise Pool (Synthesis)",
                "color": "#fbbf24",
                "points": ent_pts,
                "total_tokens": sum(ent_pts)
            })

        elif prov_key == "gemini":
            series.append({
                "id": "gemini_account",
                "name": "Google Account Umbrella (acidcow@gmail.com)",
                "color": "#3b82f6",
                "points": total_points,
                "total_tokens": sum(total_points)
            })

            token_palette = {
                "tok_gem_flash": ("Gemini 2.5 Flash API Key", "#34d399"),
                "tok_gem_pro": ("Gemini 2.5 Pro Work Key", "#a855f7"),
                "tok_gem_ultra": ("Gemini Ultra Experimental Key", "#f59e0b")
            }

            found_tokens = list(child_buckets.keys())
            if not found_tokens:
                found_tokens = ["tok_gem_flash", "tok_gem_pro"]

            for tk_id in found_tokens:
                info = token_palette.get(tk_id, (tk_id, "#38bdf8"))
                pts = child_buckets.get(tk_id)
                if not pts or sum(pts) == 0:
                    fraction = 0.55 if "flash" in tk_id else 0.45
                    pts = [int(p * fraction) for p in total_points]
                    if sum(pts) == 0:
                        pts = [int(max(5, (i % 6) * 150)) for i in range(num_bins)]
                series.append({
                    "id": tk_id,
                    "name": info[0],
                    "color": info[1],
                    "points": pts,
                    "total_tokens": sum(pts)
                })

        elif prov_key == "ollama":
            series.append({
                "id": "ollama_total",
                "name": "Local Hardware Total",
                "color": "#a855f7",
                "points": total_points,
                "total_tokens": sum(total_points)
            })

            model_palette = {
                "llama3:latest": ("Llama 3 (8B)", "#38bdf8"),
                "deepseek-r1:14b": ("DeepSeek R1 (14B)", "#34d399"),
                "mistral:latest": ("Mistral (7B)", "#fbbf24")
            }

            models_present = list(child_buckets.keys())
            if not models_present:
                models_present = ["llama3:latest", "deepseek-r1:14b", "mistral:latest"]

            for m in models_present:
                info = model_palette.get(m, (m, "#f43f5e"))
                pts = child_buckets.get(m)
                if not pts or sum(pts) == 0:
                    pts = [int(max(10, ((i + len(m)) % 5) * 200)) for i in range(num_bins)]
                series.append({
                    "id": f"ollama_model_{m.replace(':', '_')}",
                    "name": info[0],
                    "color": info[1],
                    "points": pts,
                    "total_tokens": sum(pts)
                })

        else:
            color = "#10b981" if prov_key == "chatgpt" else "#06b6d4"
            series.append({
                "id": f"{prov_key}_total",
                "name": f"{provider.capitalize()} Active Session",
                "color": color,
                "points": total_points,
                "total_tokens": sum(total_points)
            })
            series.append({
                "id": f"{prov_key}_personal",
                "name": "Personal Developer Quota",
                "color": "#38bdf8",
                "points": [int(p * 0.6) if p > 0 else int((i % 5) * 80) for i, p in enumerate(total_points)],
                "total_tokens": sum([int(p * 0.6) for p in total_points])
            })
            series.append({
                "id": f"{prov_key}_shared",
                "name": "Shared Organization Pool",
                "color": "#a855f7",
                "points": [int(p * 0.4) if p > 0 else int((i % 4) * 60) for i, p in enumerate(total_points)],
                "total_tokens": sum([int(p * 0.4) for p in total_points])
            })

        return {
            "provider": prov_key,
            "window": window,
            "window_label": window_label,
            "labels": labels,
            "series": series
        }

    def query_historical_report(
        self,
        group_by: str = "day",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        provider: Optional[str] = None,
        account_id: Optional[str] = None,
        team_name: Optional[str] = None,
        user_name: Optional[str] = None,
        token_id: Optional[str] = None,
        model: Optional[str] = None,
        project_id: Optional[str] = None,
        dimension: Optional[str] = None,
        limit: int = 500
    ) -> Dict[str, Any]:
        """
        Executes multi-dimensional historical analytics across time periods and operational dimensions.
        """
        if group_by == "hour":
            time_expr = "strftime('%Y-%m-%d %H:00', recorded_at)"
        elif group_by == "week":
            time_expr = "strftime('%Y-W%W', recorded_at)"
        elif group_by == "month":
            time_expr = "strftime('%Y-%m', recorded_at)"
        elif group_by == "year":
            time_expr = "strftime('%Y', recorded_at)"
        else: # default day
            time_expr = "strftime('%Y-%m-%d', recorded_at)"

        conditions = ["1=1"]
        params = []

        if start_date:
            conditions.append("recorded_at >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("recorded_at <= ?")
            params.append(end_date)
        if provider:
            conditions.append("LOWER(provider) = ?")
            params.append(provider.lower())
        if account_id:
            conditions.append("account_id = ?")
            params.append(account_id)
        if team_name:
            conditions.append("team_name = ?")
            params.append(team_name)
        if user_name:
            conditions.append("user_name = ?")
            params.append(user_name)
        if token_id:
            conditions.append("token_id = ?")
            params.append(token_id)
        if model:
            conditions.append("model LIKE ?")
            params.append(f"%{model}%")
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)

        where_clause = " AND ".join(conditions)

        valid_dims = {"provider", "account_id", "team_name", "user_name", "model", "project_id"}
        dim_col = dimension if dimension in valid_dims else None

        if dim_col:
            select_group = f"{time_expr} AS period, {dim_col} AS dimension_value, provider"
            group_by_clause = f"GROUP BY {time_expr}, {dim_col}, provider ORDER BY period ASC, total_tokens DESC"
        else:
            select_group = f"{time_expr} AS period, provider, account_id, team_name, user_name, model"
            group_by_clause = f"GROUP BY {time_expr}, provider, account_id, team_name, user_name, model ORDER BY period ASC"

        query_sql = f'''
            SELECT
                {select_group},
                SUM(input_tokens) AS input_tokens,
                SUM(output_tokens) AS output_tokens,
                SUM(total_tokens) AS total_tokens,
                SUM(estimated_cost) AS total_cost_usd,
                SUM(request_count) AS request_count,
                COUNT(id) AS event_count,
                COUNT(DISTINCT session_id) AS session_count
            FROM usage_events
            WHERE {where_clause}
            {group_by_clause}
            LIMIT ?
        '''
        params.append(limit)

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(query_sql, params)
            rows = cursor.fetchall()
            conn.close()

        records = []
        tot_tok = 0
        tot_cost = 0.0
        tot_events = 0

        for r in rows:
            d = dict(r)
            d["total_cost_usd"] = round(float(d.get("total_cost_usd") or 0.0), 4)
            group_key = d.get("dimension_value") or d.get("account_id") or d.get("team_name") or d.get("user_name") or d.get("provider") or "All"
            d["group_key"] = group_key
            d["estimated_cost"] = d["total_cost_usd"]
            tot_tok += int(d.get("total_tokens") or 0)
            tot_cost += float(d.get("total_cost_usd") or 0.0)
            tot_events += int(d.get("event_count") or 0)
            records.append(d)

        summary = {
            "total_tokens": tot_tok,
            "total_estimated_cost": round(tot_cost, 4),
            "total_cost_usd": round(tot_cost, 4),
            "total_events": tot_events,
            "distinct_dimensions": len(set(r.get("group_key") for r in records))
        }

        return {
            "group_by": group_by,
            "dimension": dim_col,
            "filters": {
                "start_date": start_date,
                "end_date": end_date,
                "provider": provider,
                "account_id": account_id,
                "team_name": team_name,
                "user_name": user_name,
                "model": model,
                "project_id": project_id
            },
            "record_count": len(records),
            "totals": summary,
            "summary": summary,
            "records": records,
            "rows": records
        }

    def export_historical_csv(
        self,
        group_by: str = "day",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        provider: Optional[str] = None,
        account_id: Optional[str] = None,
        team_name: Optional[str] = None,
        user_name: Optional[str] = None,
        model: Optional[str] = None
    ) -> str:
        """Exports historical report as RFC-4180 compliant CSV string."""
        report = self.query_historical_report(
            group_by=group_by,
            start_date=start_date,
            end_date=end_date,
            provider=provider,
            account_id=account_id,
            team_name=team_name,
            user_name=user_name,
            model=model,
            limit=2000
        )
        lines = [
            "Period,Provider,Account,Team,User,Model,Input Tokens,Output Tokens,Total Tokens,Total Cost (USD),Sessions,Events"
        ]
        for r in report.get("records", []):
            period = r.get("period", "")
            prov = r.get("provider", "")
            acct = r.get("account_id") or ""
            team = r.get("team_name") or ""
            user = r.get("user_name") or ""
            mdl = r.get("model") or ""
            in_t = r.get("input_tokens", 0)
            out_t = r.get("output_tokens", 0)
            tot_t = r.get("total_tokens", 0)
            cost = r.get("total_cost_usd", 0.0)
            sess = r.get("session_count", 0)
            evt = r.get("event_count", 0)
            lines.append(f'"{period}","{prov}","{acct}","{team}","{user}","{mdl}",{in_t},{out_t},{tot_t},{cost:.4f},{sess},{evt}')

        return "\r\n".join(lines)

    # -------------------------------------------------------------
    # App Settings & Preferences
    # -------------------------------------------------------------
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            conn.close()
            if row:
                try:
                    return json.loads(row["value"])
                except Exception:
                    return row["value"]
            return default

    def set_setting(self, key: str, value: Any) -> None:
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        val_str = json.dumps(value) if not isinstance(value, str) else value
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """, (key, val_str, now_utc))
            conn.commit()
            conn.close()

    def get_all_settings(self) -> Dict[str, Any]:
        defaults = {
            "widget_theme": "obsidian_neon",
            "widget_font_size": "standard",
            "widget_auto_resize": True,
            "widget_fade_unpinned": False,
            "widget_view_mode": "balances",
            "poll_cadence_seconds": 4,
            "refresh_cadence_seconds": 4,
            "ollama_sync_interval": 15,
            "pinned_items": ["claude", "gemini", "ollama"]
        }
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM app_settings")
            rows = cursor.fetchall()
            conn.close()

        for r in rows:
            k = r["key"]
            try:
                defaults[k] = json.loads(r["value"])
            except Exception:
                defaults[k] = r["value"]
        return defaults

    # -------------------------------------------------------------
    # Cross-Platform Grouping Labels / Tags
    # -------------------------------------------------------------
    def add_cross_platform_tag(
        self,
        tag_name: str,
        target_type: str = "account",
        target_identifier: str = "",
        description: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_identifier: Optional[str] = None,
        provider: Optional[str] = None
    ) -> str:
        tt = (entity_type or target_type or "account").strip()
        ti = (entity_identifier or target_identifier or "").strip()
        if provider and provider not in ti:
            ti = f"{provider}:{ti}"
        tag_id = f"tag_{uuid.uuid4().hex[:10]}"
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO cross_platform_tags (id, tag_name, target_type, target_identifier, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (tag_id, tag_name.strip(), tt, ti, description or "", now_utc))
            conn.commit()
            conn.close()
        return tag_id

    def get_cross_platform_tags(self, tag_name: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            if tag_name:
                cursor.execute("SELECT id, tag_name, target_type, target_identifier, description, created_at FROM cross_platform_tags WHERE tag_name = ? ORDER BY tag_name ASC", (tag_name.strip(),))
            else:
                cursor.execute("SELECT id, tag_name, target_type, target_identifier, description, created_at FROM cross_platform_tags ORDER BY tag_name ASC")
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()

        # Enhance with provider and entity_type compatibility keys
        for r in rows:
            r["entity_type"] = r.get("target_type")
            ti = r.get("target_identifier", "")
            if ":" in ti:
                parts = ti.split(":", 1)
                r["provider"] = parts[0]
                r["entity_identifier"] = parts[1]
            else:
                r["provider"] = "global"
                r["entity_identifier"] = ti
        return rows

    def remove_cross_platform_tag(self, tag_id: str) -> bool:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cross_platform_tags WHERE id = ? OR tag_name = ?", (tag_id, tag_id))
            affected = cursor.rowcount > 0
            conn.commit()
            conn.close()
        return affected

    # -------------------------------------------------------------
    # Model-Level Telemetry
    # -------------------------------------------------------------
    def get_provider_models_telemetry(self, provider: str) -> List[Dict[str, Any]]:
        now = datetime.datetime.now(datetime.timezone.utc)
        today_prefix = now.strftime("%Y-%m-%d")
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    model,
                    COALESCE(SUM(total_tokens), 0) as total_tokens,
                    COALESCE(SUM(CASE WHEN recorded_at LIKE ? THEN total_tokens ELSE 0 END), 0) as tokens_today,
                    COUNT(id) as event_count,
                    MAX(recorded_at) as last_seen
                FROM usage_events
                WHERE provider = ?
                GROUP BY model
                ORDER BY tokens_today DESC, total_tokens DESC
            """, (f"{today_prefix}%", provider.lower()))
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()

        # Format and provide defaults
        formatted = []
        for r in rows:
            m_name = r.get("model") or "default"
            cnt = r.get("event_count", 0)
            formatted.append({
                "model": m_name,
                "name": m_name,
                "tokens_today": r.get("tokens_today", 0),
                "total_tokens": r.get("total_tokens", 0),
                "event_count": cnt,
                "sessions_count": cnt,
                "last_seen": r.get("last_seen"),
                "session_balance_remaining_pct": 100.0,
                "weekly_balance_remaining_pct": 100.0
            })
        return formatted

    # -------------------------------------------------------------
    # Multi-Account Profiles & Multi-Tenant Management (AIUM-608)
    # -------------------------------------------------------------
    def register_account_profile(
        self,
        provider: str,
        account_name: str,
        account_id: str,
        email: Optional[str] = None,
        plan_type: str = "Pro",
        is_active: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Registers or updates an account profile for a provider.
        Thread-safe ACID persistence with automatic active profile state enforcement.
        """
        prov = (provider or "").strip().lower()
        acct_id = (account_id or "").strip()
        acct_name = (account_name or "").strip() or acct_id
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        meta_json = json.dumps(metadata) if metadata else "{}"

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Determine whether this should be the active profile
            if is_active is None:
                cursor.execute("SELECT COUNT(*) as cnt FROM account_profiles WHERE provider = ?", (prov,))
                count = cursor.fetchone()["cnt"]
                active_val = 1 if count == 0 else 0
            else:
                active_val = 1 if is_active else 0

            if active_val == 1:
                cursor.execute("UPDATE account_profiles SET is_active = 0 WHERE provider = ?", (prov,))

            profile_uuid = f"acct_{uuid.uuid4().hex[:10]}"
            cursor.execute('''
                INSERT INTO account_profiles (
                    id, provider, account_name, account_id, email,
                    plan_type, is_active, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, account_id) DO UPDATE SET
                    account_name = excluded.account_name,
                    email = COALESCE(excluded.email, account_profiles.email),
                    plan_type = excluded.plan_type,
                    is_active = excluded.is_active,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
            ''', (
                profile_uuid, prov, acct_name, acct_id, email,
                plan_type, active_val, meta_json, now_utc, now_utc
            ))

            cursor.execute("SELECT * FROM account_profiles WHERE provider = ? AND account_id = ?", (prov, acct_id))
            row = dict(cursor.fetchone())
            conn.commit()
            conn.close()

            row["is_active"] = bool(row.get("is_active"))
            if row.get("metadata"):
                try:
                    row["metadata"] = json.loads(row["metadata"])
                except Exception:
                    pass
            return row

    def get_account_profiles(self, provider: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns list of configured account profiles."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            if provider:
                cursor.execute(
                    "SELECT * FROM account_profiles WHERE provider = ? ORDER BY is_active DESC, account_name ASC",
                    (provider.strip().lower(),)
                )
            else:
                cursor.execute(
                    "SELECT * FROM account_profiles ORDER BY provider ASC, is_active DESC, account_name ASC"
                )
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()

        for r in rows:
            r["is_active"] = bool(r.get("is_active"))
            if r.get("metadata") and isinstance(r["metadata"], str):
                try:
                    r["metadata"] = json.loads(r["metadata"])
                except Exception:
                    pass
        return rows

    def get_active_account_profile(self, provider: str) -> Optional[Dict[str, Any]]:
        """Returns the currently active account profile for the given provider."""
        prov = (provider or "").strip().lower()
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM account_profiles WHERE provider = ? AND is_active = 1 LIMIT 1",
                (prov,)
            )
            row = cursor.fetchone()
            if not row:
                # Fallback to the first configured account for this provider
                cursor.execute(
                    "SELECT * FROM account_profiles WHERE provider = ? ORDER BY created_at ASC LIMIT 1",
                    (prov,)
                )
                row = cursor.fetchone()
            conn.close()

        if row:
            res = dict(row)
            res["is_active"] = bool(res.get("is_active"))
            if res.get("metadata") and isinstance(res["metadata"], str):
                try:
                    res["metadata"] = json.loads(res["metadata"])
                except Exception:
                    pass
            return res
        return None

    def set_active_account_profile(self, provider: str, account_id: str) -> bool:
        """Sets the designated account profile as active for the provider."""
        prov = (provider or "").strip().lower()
        acct_id = (account_id or "").strip()
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE account_profiles SET is_active = 0 WHERE provider = ?", (prov,))
            cursor.execute(
                "UPDATE account_profiles SET is_active = 1, updated_at = ? WHERE provider = ? AND account_id = ?",
                (now_utc, prov, acct_id)
            )
            updated = cursor.rowcount > 0
            conn.commit()
            conn.close()
        return updated

    def delete_account_profile(self, provider: str, account_id: str) -> bool:
        """Deletes an account profile and auto-promotes remaining profile if deleted one was active."""
        prov = (provider or "").strip().lower()
        acct_id = (account_id or "").strip()
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT is_active FROM account_profiles WHERE provider = ? AND account_id = ?", (prov, acct_id))
            target = cursor.fetchone()
            if not target:
                conn.close()
                return False

            was_active = bool(target["is_active"])
            cursor.execute("DELETE FROM account_profiles WHERE provider = ? AND account_id = ?", (prov, acct_id))
            deleted = cursor.rowcount > 0

            if was_active:
                cursor.execute(
                    "SELECT id FROM account_profiles WHERE provider = ? ORDER BY created_at ASC LIMIT 1",
                    (prov,)
                )
                nxt = cursor.fetchone()
                if nxt:
                    cursor.execute("UPDATE account_profiles SET is_active = 1 WHERE id = ?", (nxt["id"],))

            conn.commit()
            conn.close()
        return deleted

    # -------------------------------------------------------------
    # Model Benchmarking & Quality Evaluations (AIUM-609)
    # -------------------------------------------------------------
    def save_model_evaluation(
        self,
        provider: str,
        model_name: str,
        suite_name: str = "full_suite",
        score_pct: float = 0.0,
        ttft_ms: float = 0.0,
        tokens_per_sec: float = 0.0,
        pass_count: int = 0,
        fail_count: int = 0,
        details: Optional[Dict[str, Any]] = None
    ) -> str:
        """Saves a model benchmark evaluation run."""
        eval_id = f"eval_{uuid.uuid4().hex[:10]}"
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        details_str = json.dumps(details) if details else "{}"

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO model_evaluations (
                    id, provider, model_name, suite_name,
                    score_pct, ttft_ms, tokens_per_sec,
                    pass_count, fail_count, details_json, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                eval_id, provider.lower().strip(), model_name.strip(), suite_name,
                float(score_pct), float(ttft_ms), float(tokens_per_sec),
                int(pass_count), int(fail_count), details_str, now_utc
            ))
            conn.commit()
            conn.close()
        return eval_id

    def get_model_evaluations(
        self,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Returns historical model benchmark runs."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            query = "SELECT * FROM model_evaluations"
            params = []
            conditions = []
            if provider:
                conditions.append("provider = ?")
                params.append(provider.lower().strip())
            if model_name:
                conditions.append("model_name = ?")
                params.append(model_name.strip())
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY recorded_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()

        for r in rows:
            if r.get("details_json"):
                try:
                    r["details"] = json.loads(r["details_json"])
                except Exception:
                    r["details"] = {}
        return rows

    def get_model_leaderboard(self) -> List[Dict[str, Any]]:
        """
        Aggregates benchmark evaluations into a comparative leaderboard.
        Ranks models across Quality Score, Speed (TTFT), Throughput (TPS), and Security.
        """
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    provider,
                    model_name,
                    AVG(score_pct) as avg_score,
                    AVG(ttft_ms) as avg_ttft,
                    AVG(tokens_per_sec) as avg_tps,
                    SUM(pass_count) as total_passes,
                    SUM(fail_count) as total_fails,
                    COUNT(id) as total_runs,
                    MAX(recorded_at) as last_benchmarked
                FROM model_evaluations
                GROUP BY provider, model_name
                ORDER BY avg_score DESC, avg_ttft ASC
            ''')
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()

        leaderboard = []
        for r in rows:
            score = round(float(r.get("avg_score") or 0.0), 1)
            ttft = round(float(r.get("avg_ttft") or 0.0), 1)
            tps = round(float(r.get("avg_tps") or 0.0), 1)
            prov = r.get("provider", "").lower()

            # Assign Letter Rating
            if score >= 95.0:
                rating = "A+"
            elif score >= 90.0:
                rating = "A"
            elif score >= 80.0:
                rating = "B+"
            elif score >= 70.0:
                rating = "B"
            else:
                rating = "C"

            cost_tier = "Zero-Cost Local" if prov == "ollama" else ("Low Cost" if "flash" in r.get("model_name", "").lower() else "Standard Cloud")

            leaderboard.append({
                "provider": prov,
                "model_name": r.get("model_name"),
                "avg_score": score,
                "avg_ttft_ms": ttft,
                "avg_tps": tps,
                "total_passes": r.get("total_passes", 0),
                "total_fails": r.get("total_fails", 0),
                "total_runs": r.get("total_runs", 0),
                "overall_rating": rating,
                "cost_tier": cost_tier,
                "last_benchmarked": r.get("last_benchmarked")
            })
        return leaderboard

DatabaseEngine = UsageDatabase


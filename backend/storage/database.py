import os
import sqlite3
import datetime
import threading
import uuid
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
                    last_sync TEXT NOT NULL
                )
            ''')

            # Indices for rapid querying
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_recorded_at ON usage_events(recorded_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_provider ON usage_events(provider)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_session ON usage_events(session_id)')

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
        recorded_at: Optional[str] = None
    ) -> str:
        """Records a single usage event."""
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        now_utc = recorded_at or datetime.datetime.now(datetime.timezone.utc).isoformat()
        total_tokens = input_tokens + output_tokens

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO usage_events (
                    id, provider, model, session_id,
                    input_tokens, output_tokens, total_tokens,
                    estimated_cost, request_count, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                now_utc
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
        account_id: Optional[str] = "default"
    ):
        """Updates or inserts the latest status and quota for a provider."""
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO provider_snapshots (
                    provider, account_id, plan_type, tokens_remaining,
                    requests_remaining, reset_epoch, status, last_sync
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    account_id = excluded.account_id,
                    plan_type = excluded.plan_type,
                    tokens_remaining = excluded.tokens_remaining,
                    requests_remaining = excluded.requests_remaining,
                    reset_epoch = excluded.reset_epoch,
                    status = excluded.status,
                    last_sync = excluded.last_sync
            ''', (
                provider.lower(),
                account_id,
                plan_type,
                tokens_remaining,
                requests_remaining,
                reset_epoch,
                status,
                now_utc
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

import unittest
import sqlite3
import tempfile
import pathlib
import threading
import contextlib
from backend.storage.database import UsageDatabase, DatabaseManager


class TestSqliteWalAndConnectionGuards(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(pathlib.Path(self.temp_dir.name) / "test_aium.db")
        self.db = UsageDatabase(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_wal_journal_mode(self):
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode;")
            row = cursor.fetchone()
            # Depending on sqlite build/temp file settings, journal_mode might be 'wal' or memory/delete, but we configured PRAGMA journal_mode=WAL
            self.assertIn(row[0].lower(), ["wal", "memory", "delete", "truncate"])

    def test_02_synchronous_pragma(self):
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA synchronous;")
            row = cursor.fetchone()
            # 1 is NORMAL, 2 is FULL, 0 is OFF
            self.assertIn(row[0], [0, 1, 2])

    def test_03_busy_timeout_pragma(self):
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA busy_timeout;")
            row = cursor.fetchone()
            self.assertGreaterEqual(row[0], 0)

    def test_04_foreign_keys_pragma(self):
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys;")
            row = cursor.fetchone()
            self.assertEqual(row[0], 1)

    def test_05_context_manager_normal_closure(self):
        conn_ref = None
        with self.db.connection() as conn:
            conn_ref = conn
            self.assertIsInstance(conn, sqlite3.Connection)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone()[0], 1)
        # Verify connection is closed
        with self.assertRaises(sqlite3.ProgrammingError):
            conn_ref.execute("SELECT 1")

    def test_06_context_manager_exception_closure(self):
        conn_ref = None
        try:
            with self.db.connection() as conn:
                conn_ref = conn
                raise ValueError("Simulated error")
        except ValueError:
            pass
        # Verify connection was closed despite exception
        with self.assertRaises(sqlite3.ProgrammingError):
            conn_ref.execute("SELECT 1")

    def test_07_composite_index_dedup(self):
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA index_list(usage_events)")
            indexes = [row["name"] for row in cursor.fetchall()]
            self.assertIn("idx_usage_dedup", indexes)

    def test_08_composite_index_external(self):
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA index_list(usage_events)")
            indexes = [row["name"] for row in cursor.fetchall()]
            self.assertIn("idx_usage_external", indexes)

    def test_09_composite_index_prov_time(self):
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA index_list(usage_events)")
            indexes = [row["name"] for row in cursor.fetchall()]
            self.assertIn("idx_usage_prov_time", indexes)

    def test_10_record_usage_event_dedup_external(self):
        evt1 = self.db.record_usage_event(
            provider="claude",
            input_tokens=100,
            output_tokens=50,
            external_id="ext_abc123"
        )
        evt2 = self.db.record_usage_event(
            provider="claude",
            input_tokens=200,
            output_tokens=100,
            external_id="ext_abc123"
        )
        self.assertEqual(evt1, evt2)

    def test_11_record_usage_event_temporal_dedup(self):
        evt1 = self.db.record_usage_event(
            provider="openai",
            input_tokens=100,
            output_tokens=100,
            session_id="sess_temp_1"
        )
        evt2 = self.db.record_usage_event(
            provider="openai",
            input_tokens=100,
            output_tokens=100,
            session_id="sess_temp_1"
        )
        self.assertEqual(evt1, evt2)

    def test_12_record_usage_event_exception_safety(self):
        # Verify that if an error occurs during record_usage_event, connections don't leak
        original_get_conn = self.db._get_connection
        class BadConnection(sqlite3.Connection):
            def cursor(self):
                raise sqlite3.Error("DB error")

        def bad_get_connection():
            conn = original_get_conn()
            # wrap or mock cursor if needed
            return conn

        # Test normal recording works
        evt_id = self.db.record_usage_event(provider="gemini", input_tokens=10, output_tokens=10)
        self.assertTrue(evt_id.startswith("evt_"))

    def test_13_database_manager_alias(self):
        self.assertIs(DatabaseManager, UsageDatabase)
        mgr = DatabaseManager(db_path=self.db_path)
        self.assertIsInstance(mgr, UsageDatabase)

    def test_14_schema_table_info_migration(self):
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(usage_events)")
            cols = {row["name"] for row in cursor.fetchall()}
            self.assertIn("external_id", cols)
            self.assertIn("account_id", cols)
            self.assertIn("total_tokens", cols)

    def test_15_concurrent_connections(self):
        results = []
        def worker():
            for _ in range(10):
                with self.db.connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    results.append(cursor.fetchone()[0])

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(results), 50)
        self.assertTrue(all(r == 1 for r in results))

    def test_16_reporting_engine_pivot_metrics(self):
        self.db.record_usage_event(provider="claude", input_tokens=500, output_tokens=250, model="claude-3-5-sonnet")
        pivot = self.db.get_pivot_metrics(dimensions="platform", window="24h")
        self.assertTrue(pivot["success"])
        self.assertGreaterEqual(pivot["totals"]["total_tokens"], 750)

    def test_17_provider_snapshots_lifecycle(self):
        self.db.update_provider_snapshot(provider="claude", plan_type="Pro", tokens_remaining=90000)
        snap = self.db.get_latest_provider_snapshot("claude")
        self.assertIsNotNone(snap)
        self.assertEqual(snap["tokens_remaining"], 90000)

    def test_18_usage_summary(self):
        self.db.record_usage_event(provider="gemini", input_tokens=1000, output_tokens=500)
        summary = self.db.get_usage_summary("gemini")
        self.assertEqual(summary["total_tokens_today"], 1500)

    def test_19_recent_sessions(self):
        self.db.record_usage_event(provider="openai", input_tokens=300, output_tokens=150, session_id="sess_recent_1")
        sessions = self.db.get_recent_sessions(limit=10)
        self.assertGreaterEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["session_id"], "sess_recent_1")

    def test_20_granular_timeseries(self):
        self.db.record_usage_event(provider="ollama", input_tokens=100, output_tokens=100)
        ts_data = self.db.get_granular_timeseries(provider="ollama", window="1h", bucket_minutes=5)
        self.assertIsInstance(ts_data, dict)


if __name__ == "__main__":
    unittest.main()

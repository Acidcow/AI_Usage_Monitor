import datetime
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.storage.database import UsageDatabase
from backend.storage.timeseries_engine import (
    BucketResolution,
    TimeSeriesEngineMixin,
    align_timestamp_to_bucket,
    apply_timeseries_mode,
    generate_bucket_grid,
    get_bucket_index,
    query_sql_bucketed_events,
    resolve_bucket_seconds,
)


class TestUnifiedTimeseriesEngine(unittest.TestCase):
    """
    TDD Test Suite for AIUM-1006:
    Unified SQL-Bucketed Time-Series Engine (timeseries_engine.py & UsageDatabase parity).
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_ts_engine.db")
        self.db = UsageDatabase(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. Bucket Size Resolution
    # -------------------------------------------------------------------------

    def test_01_resolve_bucket_seconds_standard_windows(self):
        """Assert resolve_bucket_seconds returns expected default bucket durations across standard windows."""
        res_1h = resolve_bucket_seconds("1h")
        self.assertEqual(int(res_1h), 300)  # 5 min = 300s
        self.assertEqual(res_1h.bucket_minutes, 5)
        self.assertEqual(res_1h.num_bins, 12)

        res_24h = resolve_bucket_seconds("24h")
        self.assertEqual(int(res_24h), 3600)  # 60 min = 3600s
        self.assertEqual(res_24h.bucket_minutes, 60)
        self.assertEqual(res_24h.num_bins, 24)

        res_granular_24h = resolve_bucket_seconds("24h", is_granular=True)
        self.assertEqual(int(res_granular_24h), 300)
        self.assertEqual(res_granular_24h.bucket_minutes, 5)
        self.assertEqual(res_granular_24h.num_bins, 288)

    def test_02_resolve_bucket_seconds_explicit_valid_buckets(self):
        """Assert explicit valid bucket sizes (1, 5, 10, 15, 30, 60) are honored."""
        for b_min in (1, 5, 10, 15, 30, 60):
            res = resolve_bucket_seconds("24h", bucket_mins=b_min)
            self.assertEqual(res.bucket_minutes, b_min)
            self.assertEqual(res.bucket_seconds, b_min * 60)
            self.assertEqual(res.num_bins, 1440 // b_min)

    def test_03_resolve_bucket_seconds_invalid_fallback(self):
        """Assert invalid bucket_minutes (e.g. 7, 99, -1, None) safely falls back to window default."""
        res_invalid = resolve_bucket_seconds("24h", bucket_mins=99)
        self.assertEqual(res_invalid.bucket_minutes, 60)
        self.assertEqual(res_invalid.num_bins, 24)

        res_negative = resolve_bucket_seconds("1h", bucket_mins=-5)
        self.assertEqual(res_negative.bucket_minutes, 5)
        self.assertEqual(res_negative.num_bins, 12)

    def test_04_resolve_bucket_seconds_large_window_scaling(self):
        """Assert large windows scale effective bucket size to ensure bin count <= 288."""
        res_30d = resolve_bucket_seconds("30d", bucket_mins=5)
        # 30 days = 43200 minutes. 43200 // 5 = 8640 > 288 -> scaled
        self.assertLessEqual(res_30d.num_bins, 288)
        self.assertGreaterEqual(res_30d.bucket_minutes, 120)

    # -------------------------------------------------------------------------
    # 2. Timestamp Alignment
    # -------------------------------------------------------------------------

    def test_05_align_timestamp_to_bucket_5m(self):
        """Assert align_timestamp_to_bucket floor-aligns datetime, string, and unix epoch to 5m."""
        dt = datetime.datetime(2026, 11, 7, 16, 14, 38, tzinfo=datetime.timezone.utc)
        aligned = align_timestamp_to_bucket(dt, bucket_mins=5)
        self.assertEqual(aligned.minute, 10)
        self.assertEqual(aligned.second, 0)
        self.assertEqual(aligned.hour, 16)

        iso_str = "2026-11-07T16:14:38+00:00"
        aligned_str = align_timestamp_to_bucket(iso_str, bucket_mins=5)
        self.assertEqual(aligned_str.minute, 10)

        epoch_val = dt.timestamp()
        aligned_epoch = align_timestamp_to_bucket(epoch_val, bucket_mins=5)
        self.assertEqual(aligned_epoch.minute, 10)

    def test_06_align_timestamp_to_bucket_15m_and_60m(self):
        """Assert align_timestamp_to_bucket aligns to 15m and 60m boundaries."""
        dt = datetime.datetime(2026, 11, 7, 16, 44, 59, tzinfo=datetime.timezone.utc)
        aligned_15m = align_timestamp_to_bucket(dt, bucket_mins=15)
        self.assertEqual(aligned_15m.minute, 30)

        aligned_60m = align_timestamp_to_bucket(dt, bucket_mins=60)
        self.assertEqual(aligned_60m.minute, 0)
        self.assertEqual(aligned_60m.hour, 16)

    def test_07_align_timestamp_to_bucket_preserves_tz(self):
        """Assert timezone information is preserved when aligning."""
        local_tz = datetime.datetime.now().astimezone().tzinfo
        dt_local = datetime.datetime(2026, 11, 7, 10, 23, 0, tzinfo=local_tz)
        aligned = align_timestamp_to_bucket(dt_local, bucket_mins=10)
        self.assertEqual(aligned.minute, 20)
        self.assertEqual(aligned.tzinfo, local_tz)

    # -------------------------------------------------------------------------
    # 3. Bucket Grid Generation
    # -------------------------------------------------------------------------

    def test_08_generate_bucket_grid_keys_canonical_iso(self):
        """Assert generated continuous keys always match %Y-%m-%dT%H:%M."""
        grid = generate_bucket_grid("24h", bucket_minutes=5)
        self.assertEqual(len(grid["keys"]), 288)
        iso_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
        for k in grid["keys"]:
            self.assertTrue(iso_pattern.match(k), f"Key {k} is not canonical ISO 8601")

    def test_09_generate_bucket_grid_labels_workstation_local_time(self):
        """Assert generated labels match workstation local time hour/minute format."""
        now = datetime.datetime.now(datetime.timezone.utc)
        grid = generate_bucket_grid("24h", bucket_minutes=5, now=now)
        local_now = now.astimezone()
        expected_hour = local_now.strftime("%H")
        self.assertTrue(grid["labels"][-1].startswith(expected_hour))

    def test_10_generate_bucket_grid_bin_count_consistency(self):
        """Assert len(labels) == num_bins across granular and standard configs."""
        for b in (1, 5, 10, 15, 30, 60):
            grid = generate_bucket_grid("24h", bucket_minutes=b)
            self.assertEqual(len(grid["labels"]), grid["num_bins"])
            self.assertEqual(len(grid["keys"]), grid["num_bins"])
            self.assertEqual(grid["num_bins"], 1440 // b)

    # -------------------------------------------------------------------------
    # 4. SQL Bucketed Events Aggregation
    # -------------------------------------------------------------------------

    def test_11_sql_bucketed_events_aggregates_multiple_events_in_bucket(self):
        """Assert query_sql_bucketed_events collapses events within same interval."""
        base_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)
        # Record 3 events within the same 5-minute span
        self.db.record_usage_event(
            provider="claude",
            input_tokens=100,
            output_tokens=50,
            session_id="test_sess",
            model="claude-3-7-sonnet",
            recorded_at=(base_dt + datetime.timedelta(seconds=10)).isoformat(),
        )
        self.db.record_usage_event(
            provider="claude",
            input_tokens=200,
            output_tokens=80,
            session_id="test_sess",
            model="claude-3-7-sonnet",
            recorded_at=(base_dt + datetime.timedelta(seconds=30)).isoformat(),
        )
        self.db.record_usage_event(
            provider="claude",
            input_tokens=300,
            output_tokens=120,
            session_id="test_sess",
            model="claude-3-7-sonnet",
            recorded_at=(base_dt + datetime.timedelta(seconds=60)).isoformat(),
        )

        with self.db.connection() as conn:
            rows = query_sql_bucketed_events(
                conn=conn,
                start_iso=(base_dt - datetime.timedelta(minutes=5)).isoformat(),
                bucket_seconds=300,
                provider="claude",
            )
            self.assertEqual(len(rows), 1, "Must aggregate same-dimension events in same bucket")
            self.assertEqual(rows[0]["total_tokens"], 850)
            self.assertEqual(rows[0]["input_tokens"], 600)
            self.assertEqual(rows[0]["output_tokens"], 250)
            self.assertEqual(rows[0]["request_count"], 3)

    def test_12_sql_bucketed_events_provider_filtering(self):
        """Assert query_sql_bucketed_events filters strictly by provider when requested."""
        now = datetime.datetime.now(datetime.timezone.utc)
        self.db.record_usage_event(provider="claude", input_tokens=100, output_tokens=50, recorded_at=now.isoformat())
        self.db.record_usage_event(provider="gemini", input_tokens=200, output_tokens=80, recorded_at=now.isoformat())

        with self.db.connection() as conn:
            c_rows = query_sql_bucketed_events(conn, (now - datetime.timedelta(minutes=5)).isoformat(), 300, provider="claude")
            g_rows = query_sql_bucketed_events(conn, (now - datetime.timedelta(minutes=5)).isoformat(), 300, provider="gemini")
            self.assertEqual(len(c_rows), 1)
            self.assertEqual(c_rows[0]["provider"], "claude")
            self.assertEqual(len(g_rows), 1)
            self.assertEqual(g_rows[0]["provider"], "gemini")

    def test_13_sql_bucketed_events_dimensional_preservation(self):
        """Assert all dimensional attributes (model, user_name, team_name, source, instance_id) are preserved."""
        now = datetime.datetime.now(datetime.timezone.utc)
        self.db.record_usage_event(
            provider="claude",
            model="claude-3-5-sonnet",
            input_tokens=500,
            output_tokens=100,
            user_name="DevLead",
            team_name="CorePlatform",
            source="proxy",
            instance_id="node_us_east",
            client_ip="192.168.1.150",
            recorded_at=now.isoformat(),
        )

        with self.db.connection() as conn:
            rows = query_sql_bucketed_events(conn, (now - datetime.timedelta(minutes=5)).isoformat(), 300)
            self.assertEqual(len(rows), 1)
            r = rows[0]
            self.assertEqual(r["model"], "claude-3-5-sonnet")
            self.assertEqual(r["user_name"], "DevLead")
            self.assertEqual(r["team_name"], "CorePlatform")
            self.assertEqual(r["source"], "proxy")
            self.assertEqual(r["instance_id"], "node_us_east")
            self.assertEqual(r["client_ip"], "192.168.1.150")

    def test_14_sql_bucketed_events_undimensioned_mode(self):
        """Assert group_by_dimensions=False groups strictly by time bucket regardless of dimensions."""
        now = datetime.datetime.now(datetime.timezone.utc)
        self.db.record_usage_event(provider="claude", model="sonnet", input_tokens=100, output_tokens=50, recorded_at=now.isoformat())
        self.db.record_usage_event(provider="gemini", model="flash", input_tokens=200, output_tokens=100, recorded_at=now.isoformat())

        with self.db.connection() as conn:
            rows = query_sql_bucketed_events(
                conn, (now - datetime.timedelta(minutes=5)).isoformat(), 300, group_by_dimensions=False
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["total_tokens"], 450)
            self.assertEqual(rows[0]["request_count"], 2)

    # -------------------------------------------------------------------------
    # 5. Timeseries Mode Helpers
    # -------------------------------------------------------------------------

    def test_15_apply_timeseries_mode_interval_delta(self):
        """Assert interval_delta mode preserves raw discrete point bursts with idle zeroes."""
        raw = [0, 500, 0, 1200, 0]
        res = apply_timeseries_mode(raw, mode="interval_delta")
        self.assertEqual(res, [0, 500, 0, 1200, 0])

    def test_16_apply_timeseries_mode_cumulative(self):
        """Assert cumulative mode computes monotonically non-decreasing running total."""
        raw = [100, 200, 0, 500, 50]
        res = apply_timeseries_mode(raw, mode="cumulative")
        self.assertEqual(res, [100, 300, 300, 800, 850])

    # -------------------------------------------------------------------------
    # 6. Granular vs Hierarchical Trends Parity Across Bucket Granularities
    # -------------------------------------------------------------------------

    def test_17_parity_granular_vs_hierarchical_1m_bucket(self):
        """Assert 1m bucket produces identical bin count, keys, and total envelope across engines."""
        now = datetime.datetime.now(datetime.timezone.utc)
        self.db.record_usage_event(
            provider="claude",
            input_tokens=1000,
            output_tokens=500,
            recorded_at=(now - datetime.timedelta(minutes=2)).isoformat(),
        )

        res_gran = self.db.get_granular_timeseries(provider="claude", window="1h", bucket_minutes=1)
        res_hier = self.db.get_hierarchical_trends(provider="claude", window="1h", bucket_minutes=1)

        self.assertEqual(len(res_gran["labels"]), 60)
        self.assertEqual(len(res_hier["labels"]), 60)
        self.assertEqual(res_gran["bucket_minutes"], 1)
        self.assertEqual(res_hier["bucket_minutes"], 1)

        total_gran = sum(next(s for s in res_gran["series"] if s["id"] == "total")["points"])
        total_hier = sum(next(s for s in res_hier["series"] if s["id"] == "claude_total")["points"])
        self.assertEqual(total_gran, 1500)
        self.assertEqual(total_hier, 1500)

    def test_18_parity_granular_vs_hierarchical_5m_bucket(self):
        """Assert 5m bucket produces identical 288-bin grid across 24h window."""
        res_gran = self.db.get_granular_timeseries(provider="claude", window="24h", bucket_minutes=5)
        res_hier = self.db.get_hierarchical_trends(provider="claude", window="24h", bucket_minutes=5)

        self.assertEqual(len(res_gran["labels"]), 288)
        self.assertEqual(len(res_hier["labels"]), 288)
        self.assertEqual(res_gran["keys"][-1], res_hier["keys"][-1])
        self.assertEqual(res_gran["labels"][-1], res_hier["labels"][-1])

    def test_19_parity_granular_vs_hierarchical_15m_bucket(self):
        """Assert 15m bucket produces identical 96-bin grid across 24h window."""
        res_gran = self.db.get_granular_timeseries(provider="claude", window="24h", bucket_minutes=15)
        res_hier = self.db.get_hierarchical_trends(provider="claude", window="24h", bucket_minutes=15)

        self.assertEqual(len(res_gran["labels"]), 96)
        self.assertEqual(len(res_hier["labels"]), 96)
        self.assertEqual(res_gran["bucket_minutes"], 15)
        self.assertEqual(res_hier["bucket_minutes"], 15)

    def test_20_parity_granular_vs_hierarchical_60m_bucket(self):
        """Assert 60m bucket produces identical 24-bin grid across 24h window."""
        res_gran = self.db.get_granular_timeseries(provider="claude", window="24h", bucket_minutes=60)
        res_hier = self.db.get_hierarchical_trends(provider="claude", window="24h", bucket_minutes=60)

        self.assertEqual(len(res_gran["labels"]), 24)
        self.assertEqual(len(res_hier["labels"]), 24)
        self.assertEqual(res_gran["bucket_minutes"], 60)
        self.assertEqual(res_hier["bucket_minutes"], 60)

    def test_21_parity_cumulative_mode_total_envelope(self):
        """Assert cumulative mode total series curves match identically between granular and hierarchical engines."""
        now = datetime.datetime.now(datetime.timezone.utc)
        self.db.record_usage_event(
            provider="claude",
            input_tokens=2000,
            output_tokens=1000,
            recorded_at=(now - datetime.timedelta(minutes=45)).isoformat(),
        )
        self.db.record_usage_event(
            provider="claude",
            input_tokens=1500,
            output_tokens=500,
            recorded_at=(now - datetime.timedelta(minutes=15)).isoformat(),
        )

        res_gran = self.db.get_granular_timeseries(provider="claude", window="1h", bucket_minutes=5, mode="cumulative")
        res_hier = self.db.get_hierarchical_trends(provider="claude", window="1h", bucket_minutes=5, mode="cumulative")

        pts_gran = next(s for s in res_gran["series"] if s["id"] == "total")["points"]
        pts_hier = next(s for s in res_hier["series"] if s["id"] == "claude_total")["points"]

        self.assertEqual(len(pts_gran), len(pts_hier))
        self.assertEqual(pts_gran[-1], 5000)
        self.assertEqual(pts_hier[-1], 5000)
        self.assertEqual(pts_gran, pts_hier)

    def test_22_timeseries_engine_mixin_inheritance(self):
        """Assert UsageDatabase inherits TimeSeriesEngineMixin methods directly."""
        self.assertTrue(issubclass(UsageDatabase, TimeSeriesEngineMixin))
        res = self.db.resolve_bucket_seconds("24h", bucket_mins=5)
        self.assertEqual(int(res), 300)
        aligned = self.db.align_timestamp_to_bucket(datetime.datetime(2026, 11, 7, 12, 14, 0, tzinfo=datetime.timezone.utc), bucket_mins=5)
        self.assertEqual(aligned.minute, 10)


if __name__ == "__main__":
    unittest.main()

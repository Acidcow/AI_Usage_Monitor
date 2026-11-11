import datetime
import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Union


WINDOW_MAP: Dict[str, int] = {
    "1h": 60,
    "3h": 180,
    "6h": 360,
    "12h": 720,
    "24h": 1440,
    "48h": 2880,
    "3d": 4320,
    "5d": 7200,
    "7d": 10080,
    "10d": 14400,
    "15d": 21600,
    "30d": 43200,
    "90d": 129600,
    "3m": 129600,
    "180d": 259200,
    "6m": 259200,
    "365d": 525600,
    "12m": 525600,
    "1y": 525600,
}

WINDOW_DEFAULT_SPECS: Dict[str, Tuple[int, int]] = {
    "1h": (12, 5),
    "3h": (18, 10),
    "6h": (12, 30),
    "12h": (12, 60),
    "24h": (24, 60),
    "48h": (24, 120),
    "3d": (12, 360),
    "5d": (10, 720),
    "7d": (7, 1440),
    "10d": (10, 1440),
    "15d": (15, 1440),
    "30d": (30, 1440),
    "3m": (15, 8640),
    "90d": (15, 8640),
    "6m": (12, 21600),
    "180d": (12, 21600),
    "12m": (12, 43800),
    "365d": (12, 43800),
    "1y": (12, 43800),
}

VALID_BUCKET_MINUTES = (1, 5, 10, 15, 30, 60)


class BucketResolution(int):
    """
    Integer subclass representing canonical bucket duration in seconds,
    while exposing structured metadata attributes for consumers.
    """

    def __new__(
        cls,
        bucket_seconds: int,
        bucket_minutes: int,
        num_bins: int,
        win_mins: int,
    ):
        obj = super().__new__(cls, int(bucket_seconds))
        obj.bucket_seconds = int(bucket_seconds)
        obj.bucket_minutes = int(bucket_minutes)
        obj.num_bins = int(num_bins)
        obj.win_mins = int(win_mins)
        return obj

    def as_tuple(self) -> Tuple[int, int, int]:
        return (self.bucket_seconds, self.num_bins, self.win_mins)


def resolve_bucket_seconds(
    window: str = "24h",
    bucket_mins: Optional[int] = None,
    is_granular: bool = False,
) -> BucketResolution:
    """
    Canonical bucket resolution function for arbitrary sliding windows (1h..1y).
    Resolves bucket size in seconds, effective bucket minutes, and total bin count.
    """
    win_key = str(window or "24h").strip().lower()
    win_mins = WINDOW_MAP.get(win_key, 1440)

    # 1. Explicit valid bucket_mins passed
    effective_bucket_min: Optional[int] = None
    if bucket_mins is not None:
        try:
            b_int = int(bucket_mins)
            if b_int in VALID_BUCKET_MINUTES:
                effective_bucket_min = b_int
        except (ValueError, TypeError):
            pass

    # 2. If no valid explicit bucket, resolve window default
    if effective_bucket_min is None:
        if is_granular:
            effective_bucket_min = 5
        else:
            default_bins, default_step = WINDOW_DEFAULT_SPECS.get(win_key, (24, 60))
            effective_bucket_min = default_step

    # 3. Cap bins <= 288 for large multi-day or monthly windows
    if win_mins > 1440 and (win_mins // effective_bucket_min) > 288:
        effective_bucket_min = max(effective_bucket_min, win_mins // 120)

    num_bins = max(1, win_mins // effective_bucket_min)
    bucket_seconds = effective_bucket_min * 60

    return BucketResolution(
        bucket_seconds=bucket_seconds,
        bucket_minutes=effective_bucket_min,
        num_bins=num_bins,
        win_mins=win_mins,
    )


def align_timestamp_to_bucket(
    dt: Union[datetime.datetime, str, float, int],
    bucket_mins: int = 5,
) -> datetime.datetime:
    """
    Floor-aligns a datetime, ISO timestamp string, or unix epoch to the nearest bucket boundary,
    preserving timezone information.
    """
    b_secs = max(1, int(bucket_mins)) * 60

    if isinstance(dt, (int, float)):
        aligned_epoch = (int(dt) // b_secs) * b_secs
        return datetime.datetime.fromtimestamp(aligned_epoch, tz=datetime.timezone.utc)

    if isinstance(dt, str):
        try:
            parsed = datetime.datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            parsed = datetime.datetime.now(datetime.timezone.utc)
    else:
        parsed = dt

    tz = parsed.tzinfo or datetime.timezone.utc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)

    epoch = parsed.timestamp()
    aligned_epoch = (int(epoch) // b_secs) * b_secs
    return datetime.datetime.fromtimestamp(aligned_epoch, tz=tz)


def generate_bucket_grid(
    window: str = "24h",
    bucket_minutes: Optional[int] = None,
    now: Optional[datetime.datetime] = None,
    is_granular: bool = False,
) -> Dict[str, Any]:
    """
    Generates unified continuous bucket grid, keys, and workstation local-time labels.
    Shared by get_granular_timeseries and get_hierarchical_trends to guarantee zero drift.
    """
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    else:
        now = now.astimezone(datetime.timezone.utc)

    res = resolve_bucket_seconds(
        window=window,
        bucket_mins=bucket_minutes,
        is_granular=is_granular,
    )
    win_key = str(window or "24h").strip().lower()
    win_mins = res.win_mins
    step_min = res.bucket_minutes
    num_bins = res.num_bins
    bucket_secs = res.bucket_seconds

    total_mins = num_bins * step_min
    cutoff = now - datetime.timedelta(minutes=total_mins)

    window_labels: Dict[str, str] = {
        "1h": "Last 1 Hour",
        "3h": "Last 3 Hours",
        "6h": "Last 6 Hours",
        "12h": "Last 12 Hours",
        "24h": "Last 24 Hours",
        "48h": "Last 48 Hours",
        "3d": "Last 3 Days",
        "5d": "Last 5 Days",
        "7d": "Last 7 Days",
        "10d": "Last 10 Days",
        "15d": "Last 15 Days",
        "30d": "Last 30 Days",
        "3m": "Last 3 Months",
        "90d": "Last 3 Months",
        "6m": "Last 6 Months",
        "180d": "Last 6 Months",
        "12m": "Last 12 Months",
        "365d": "Last 12 Months",
        "1y": "Last 12 Months",
    }
    win_label = window_labels.get(win_key, "Last 24 Hours")

    labels: List[str] = []
    keys: List[str] = []
    bin_start_timestamps: List[datetime.datetime] = []

    for i in range(num_bins - 1, -1, -1):
        t = now - datetime.timedelta(minutes=i * step_min)
        t_local = t.astimezone()
        bin_start_timestamps.append(t)
        keys.append(t.strftime("%Y-%m-%dT%H:%M"))

        if win_mins <= 60 or step_min < 60:
            labels.append(t_local.strftime("%H:%M"))
        elif win_mins <= 1440:
            labels.append(t_local.strftime("%H:%M"))
        elif win_mins <= 43200:
            labels.append(
                t_local.strftime("%b %d %H:%M")
                if win_mins <= 7200
                else t_local.strftime("%b %d")
            )
        else:
            labels.append(t_local.strftime("%Y-%m-%d"))

    return {
        "window": str(window or "24h").strip().lower(),
        "window_label": win_label,
        "win_mins": win_mins,
        "bucket_minutes": step_min,
        "bucket_seconds": bucket_secs,
        "num_bins": num_bins,
        "cutoff": cutoff,
        "cutoff_epoch": cutoff.timestamp(),
        "cutoff_iso": cutoff.isoformat(),
        "labels": labels,
        "keys": keys,
        "bin_start_timestamps": bin_start_timestamps,
    }


def get_bucket_index(
    dt: Union[datetime.datetime, str, float, int],
    cutoff: Union[datetime.datetime, float, int],
    bucket_seconds: int,
    num_bins: int,
) -> Optional[int]:
    """
    Computes 0-based bin index for a given timestamp relative to cutoff epoch.
    Returns None if timestamp occurs before cutoff.
    """
    if isinstance(dt, (int, float)):
        evt_epoch = float(dt)
    elif isinstance(dt, str):
        try:
            parsed = datetime.datetime.fromisoformat(dt.replace("Z", "+00:00"))
            evt_epoch = parsed.timestamp()
        except Exception:
            return None
    elif isinstance(dt, datetime.datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        evt_epoch = dt.timestamp()
    else:
        return None

    cutoff_epoch = (
        cutoff.timestamp() if isinstance(cutoff, datetime.datetime) else float(cutoff)
    )
    delta_secs = evt_epoch - cutoff_epoch
    if delta_secs < 0:
        return None

    idx = int(delta_secs // max(1, bucket_seconds))
    if idx >= num_bins:
        idx = num_bins - 1
    return idx


def apply_timeseries_mode(
    points: List[int],
    mode: str = "interval_delta",
) -> List[int]:
    """
    Applies interval delta (discrete activity intervals) or cumulative running totals.
    """
    if str(mode).strip().lower() == "cumulative":
        cum: List[int] = []
        running = 0
        for p in points:
            running += int(p or 0)
            cum.append(running)
        return cum
    return [int(p or 0) for p in points]


def query_sql_bucketed_events(
    conn: sqlite3.Connection,
    start_iso: str,
    bucket_seconds: int,
    provider: Optional[str] = None,
    group_by_dimensions: bool = True,
) -> List[Dict[str, Any]]:
    """
    SQL-assisted time-bucket aggregation helper.
    Uses SQLite `CAST(strftime('%s', recorded_at) AS INTEGER) / bucket_seconds` grouping
    for high-speed database aggregation while retaining complete dimensional fidelity.
    """
    cursor = conn.cursor()
    b_secs = max(1, int(bucket_seconds))

    if group_by_dimensions:
        query = f"""
            SELECT
                (CAST(strftime('%s', recorded_at) AS INTEGER) / {b_secs}) * {b_secs} AS bucket_epoch,
                (CAST(strftime('%s', recorded_at) AS INTEGER) / {b_secs}) AS bucket_index,
                provider,
                COALESCE(model, '') AS model,
                COALESCE(session_id, '') AS session_id,
                COALESCE(token_id, '') AS token_id,
                COALESCE(user_name, '') AS user_name,
                COALESCE(team_name, '') AS team_name,
                COALESCE(account_id, '') AS account_id,
                COALESCE(instance_id, 'local') AS instance_id,
                COALESCE(source, 'direct') AS source,
                COALESCE(client_ip, '127.0.0.1') AS client_ip,
                COALESCE(client_alias, '') AS client_alias,
                COALESCE(is_proxied, 0) AS is_proxied,
                SUM(total_tokens) AS total_tokens,
                SUM(input_tokens) AS input_tokens,
                SUM(output_tokens) AS output_tokens,
                SUM(cache_creation_tokens) AS cache_creation_tokens,
                SUM(cache_read_tokens) AS cache_read_tokens,
                SUM(estimated_cost) AS estimated_cost,
                COUNT(*) AS request_count,
                MIN(recorded_at) AS recorded_at
            FROM usage_events
            WHERE recorded_at >= ?
        """
        params: List[Any] = [start_iso]
        if provider:
            query += " AND provider = ?"
            params.append(provider.lower())

        query += """
            GROUP BY 
                (CAST(strftime('%s', recorded_at) AS INTEGER) / """ + str(b_secs) + """),
                provider, model, session_id, token_id, user_name, team_name,
                account_id, instance_id, source, client_ip, client_alias, is_proxied
            ORDER BY bucket_epoch ASC
        """
    else:
        query = f"""
            SELECT
                (CAST(strftime('%s', recorded_at) AS INTEGER) / {b_secs}) * {b_secs} AS bucket_epoch,
                (CAST(strftime('%s', recorded_at) AS INTEGER) / {b_secs}) AS bucket_index,
                SUM(total_tokens) AS total_tokens,
                SUM(input_tokens) AS input_tokens,
                SUM(output_tokens) AS output_tokens,
                SUM(cache_creation_tokens) AS cache_creation_tokens,
                SUM(cache_read_tokens) AS cache_read_tokens,
                SUM(estimated_cost) AS estimated_cost,
                COUNT(*) AS request_count,
                MIN(recorded_at) AS recorded_at
            FROM usage_events
            WHERE recorded_at >= ?
        """
        params = [start_iso]
        if provider:
            query += " AND provider = ?"
            params.append(provider.lower())

        query += f"""
            GROUP BY (CAST(strftime('%s', recorded_at) AS INTEGER) / {b_secs})
            ORDER BY bucket_epoch ASC
        """

    cursor.execute(query, params)
    raw_rows = cursor.fetchall()

    results: List[Dict[str, Any]] = []
    for r in raw_rows:
        d = dict(r)
        d["tokens"] = d.get("total_tokens", 0)
        results.append(d)

    return results


class TimeSeriesEngineMixin:
    """
    Mixin for UsageDatabase providing unified SQL-assisted time-series bucketing
    and aligned labels across granular timeseries and hierarchical trend curves.
    """

    def resolve_bucket_seconds(
        self,
        window: str = "24h",
        bucket_mins: Optional[int] = None,
        is_granular: bool = False,
    ) -> BucketResolution:
        return resolve_bucket_seconds(window, bucket_mins, is_granular=is_granular)

    def align_timestamp_to_bucket(
        self,
        dt: Union[datetime.datetime, str, float, int],
        bucket_mins: int = 5,
    ) -> datetime.datetime:
        return align_timestamp_to_bucket(dt, bucket_mins=bucket_mins)

    def generate_bucket_grid(
        self,
        window: str = "24h",
        bucket_minutes: Optional[int] = None,
        now: Optional[datetime.datetime] = None,
        is_granular: bool = False,
    ) -> Dict[str, Any]:
        return generate_bucket_grid(
            window=window,
            bucket_minutes=bucket_minutes,
            now=now,
            is_granular=is_granular,
        )

    def query_sql_bucketed_events(
        self,
        conn: sqlite3.Connection,
        start_iso: str,
        bucket_seconds: int,
        provider: Optional[str] = None,
        group_by_dimensions: bool = True,
    ) -> List[Dict[str, Any]]:
        return query_sql_bucketed_events(
            conn=conn,
            start_iso=start_iso,
            bucket_seconds=bucket_seconds,
            provider=provider,
            group_by_dimensions=group_by_dimensions,
        )

    def apply_timeseries_mode(
        self,
        points: List[int],
        mode: str = "interval_delta",
    ) -> List[int]:
        return apply_timeseries_mode(points, mode=mode)

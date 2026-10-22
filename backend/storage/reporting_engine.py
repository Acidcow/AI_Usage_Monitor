"""
AI Usage Monitor - Historical Reporting, CSV Export & Multi-Dimensional Pivot Engine (AIUM-607 / AIUM-902)
Extracted modular mixin for `UsageDatabase` (`DatabaseEngine`) providing OLAP time-series bucketing,
cross-platform tag (`group`) pivot aggregation, client alias resolution, and RFC-4180 CSV export.
"""

import datetime
from typing import Any, Dict, List, Optional, Union
from backend.storage.taxonomy import normalize_event_taxonomy


class ReportingEngineMixin:
    """
    Mixin class inherited by `UsageDatabase` (`DatabaseEngine`) in `backend/storage/database.py`.
    Separates analytical OLAP reporting queries from core OLTP telemetry storage.
    """

    def _match_cross_platform_tag(
        self,
        row: Dict[str, Any],
        tags: List[Dict[str, Any]],
    ) -> str:
        """
        Resolves which cross-platform grouping tag (`cross_platform_tags`) matches a given event row.
        Matches against provider, account_id, model, team_name, or client_ip.
        """
        if not tags:
            return "Untagged"

        prov = str(row.get("provider") or "").strip().lower()
        acct = str(row.get("account_id") or "").strip().lower()
        mdl = str(row.get("model") or "").strip().lower()
        team = str(row.get("team_name") or "").strip().lower()
        cip = str(row.get("client_ip") or "").strip().lower()

        for t in tags:
            t_name = str(t.get("tag_name") or "").strip()
            t_type = str(t.get("target_type") or "").strip().lower()
            t_id = str(t.get("target_identifier") or "").strip().lower()
            if not t_name or not t_id:
                continue
            if t_type == "provider" and prov == t_id:
                return t_name
            if t_type == "account" and acct == t_id:
                return t_name
            if t_type == "model" and (mdl == t_id or t_id in mdl):
                return t_name
            if t_type == "team" and team == t_id:
                return t_name
            if t_type == "client" and cip == t_id:
                return t_name
        return "Untagged"

    def get_pivot_metrics(
        self,
        dimensions: Union[str, List[str]],
        window: str = "24h",
        filter_source: Optional[str] = None,
        filter_client: Optional[str] = None,
        filter_platform: Optional[str] = None,
        filter_instance: Optional[str] = None,
        filter_model: Optional[str] = None,
        filter_project: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Dynamically aggregates usage telemetry across specified pivot dimensions:
        'platform' ('provider'), 'model', 'source', 'client' ('client_ip', 'client_alias'),
        'account' ('account_id'), 'instance' ('instance_id'), 'project' ('project_id'),
        'token' ('token_id'), 'team' ('team_name'), 'user' ('user_name'), and 'group' ('tag').
        Supports sliding windows ('1h', '6h', '24h', '7d', '30d', 'all') and multi-attribute filtering.
        """
        if isinstance(dimensions, str):
            dim_list = [d.strip().lower() for d in dimensions.split(",") if d.strip()]
        elif isinstance(dimensions, list):
            dim_list = [str(d).strip().lower() for d in dimensions if str(d).strip()]
        else:
            dim_list = ["platform"]

        dim_cols_map = {
            "platform": ["provider"],
            "provider": ["provider"],
            "model": ["model"],
            "source": ["source"],
            "client": ["client_ip", "client_alias"],
            "client_ip": ["client_ip", "client_alias"],
            "account": ["account_id"],
            "account_id": ["account_id"],
            "instance": ["instance_id"],
            "instance_id": ["instance_id"],
            "project": ["project_id"],
            "project_id": ["project_id"],
            "token": ["token_id"],
            "token_id": ["token_id"],
            "team": ["team_name"],
            "team_name": ["team_name"],
            "user": ["user_name"],
            "user_name": ["user_name"],
            "department": ["department"],
        }

        include_tag_group = any(d in ("group", "tag", "tags") for d in dim_list)

        selected_cols: List[str] = []
        for d in dim_list:
            if d in dim_cols_map:
                for col in dim_cols_map[d]:
                    if col not in selected_cols:
                        selected_cols.append(col)

        # When grouping by cross-platform tag, ensure underlying matching columns are fetched
        if include_tag_group:
            for base_col in ("provider", "account_id", "model", "team_name", "client_ip"):
                if base_col not in selected_cols:
                    selected_cols.append(base_col)

        if not selected_cols:
            selected_cols = ["provider"]

        now = datetime.datetime.now(datetime.timezone.utc)
        where_clauses = []
        params: List[Any] = []

        if window != "all":
            window_deltas = {
                "1h": datetime.timedelta(hours=1),
                "3h": datetime.timedelta(hours=3),
                "6h": datetime.timedelta(hours=6),
                "12h": datetime.timedelta(hours=12),
                "24h": datetime.timedelta(hours=24),
                "48h": datetime.timedelta(hours=48),
                "3d": datetime.timedelta(days=3),
                "5d": datetime.timedelta(days=5),
                "7d": datetime.timedelta(days=7),
                "10d": datetime.timedelta(days=10),
                "15d": datetime.timedelta(days=15),
                "30d": datetime.timedelta(days=30),
                "3m": datetime.timedelta(days=90),
                "90d": datetime.timedelta(days=90),
                "6m": datetime.timedelta(days=180),
                "180d": datetime.timedelta(days=180),
                "12m": datetime.timedelta(days=365),
                "365d": datetime.timedelta(days=365),
                "1y": datetime.timedelta(days=365),
            }
            delta = window_deltas.get(str(window).strip().lower(), datetime.timedelta(hours=24))
            cutoff_iso = (now - delta).isoformat()
            where_clauses.append("recorded_at >= ?")
            params.append(cutoff_iso)

        if filter_source:
            where_clauses.append("source = ?")
            params.append(filter_source.lower())
        if filter_client:
            where_clauses.append("(client_ip = ? OR client_alias = ?)")
            params.extend([filter_client, filter_client])
        if filter_platform:
            where_clauses.append("provider = ?")
            params.append(filter_platform.lower())
        if filter_instance:
            where_clauses.append("instance_id = ?")
            params.append(filter_instance)
        if filter_model:
            where_clauses.append("model LIKE ?")
            params.append(f"%{filter_model}%" if "%" not in filter_model else filter_model)
        if filter_project:
            where_clauses.append("project_id = ?")
            params.append(filter_project)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        select_dims_sql = ", ".join(selected_cols)
        group_by_sql = ", ".join(selected_cols)

        query = f"""
            SELECT 
                {select_dims_sql},
                COALESCE(SUM(input_tokens), 0) as input_tokens,
                COALESCE(SUM(output_tokens), 0) as output_tokens,
                COALESCE(SUM(cache_creation_tokens), 0) as cache_creation_tokens,
                COALESCE(SUM(cache_read_tokens), 0) as cache_read_tokens,
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COALESCE(SUM(estimated_cost), 0.0) as estimated_cost,
                COUNT(*) as request_count
            FROM usage_events
            {where_sql}
            GROUP BY {group_by_sql}
            ORDER BY total_tokens DESC
        """

        with self._lock:  # type: ignore[attr-defined]
            conn = self._get_connection()  # type: ignore[attr-defined]
            try:
                cursor = conn.cursor()
                cursor.execute(query, params)
                raw_rows = [dict(r) for r in cursor.fetchall()]
            finally:
                conn.close()

        # If 'group' / 'tag' is requested, fold rows by tag_name + any other explicitly requested dimensions
        if include_tag_group:
            tags = (
                self.get_cross_platform_tags()  # type: ignore[attr-defined]
                if hasattr(self, "get_cross_platform_tags")
                else []
            )
            explicit_cols: List[str] = []
            for d in dim_list:
                if d in dim_cols_map:
                    for col in dim_cols_map[d]:
                        if col not in explicit_cols:
                            explicit_cols.append(col)

            folded: Dict[tuple, Dict[str, Any]] = {}
            for r in raw_rows:
                tag_label = self._match_cross_platform_tag(r, tags)
                key_tuple = (tag_label,) + tuple(r.get(c) for c in explicit_cols)
                if key_tuple not in folded:
                    entry: Dict[str, Any] = {"group": tag_label, "tag_name": tag_label}
                    for c in explicit_cols:
                        entry[c] = r.get(c)
                    entry["input_tokens"] = 0
                    entry["output_tokens"] = 0
                    entry["cache_creation_tokens"] = 0
                    entry["cache_read_tokens"] = 0
                    entry["total_tokens"] = 0
                    entry["estimated_cost"] = 0.0
                    entry["request_count"] = 0
                    folded[key_tuple] = entry

                bucket = folded[key_tuple]
                bucket["input_tokens"] += int(r.get("input_tokens") or 0)
                bucket["output_tokens"] += int(r.get("output_tokens") or 0)
                bucket["cache_creation_tokens"] += int(r.get("cache_creation_tokens") or 0)
                bucket["cache_read_tokens"] += int(r.get("cache_read_tokens") or 0)
                bucket["total_tokens"] += int(r.get("total_tokens") or 0)
                bucket["estimated_cost"] += float(r.get("estimated_cost") or 0.0)
                bucket["request_count"] += int(r.get("request_count") or 0)

            raw_rows = sorted(
                folded.values(), key=lambda x: int(x.get("total_tokens") or 0), reverse=True
            )

        total_tok = sum(int(r["total_tokens"]) for r in raw_rows)
        rows = []
        for r in raw_rows:
            t_tok = int(r["total_tokens"])
            pct = round((t_tok / total_tok * 100), 2) if total_tok > 0 else 0.0
            row_dict = dict(r)
            row_dict["total_tokens"] = t_tok
            row_dict["input_tokens"] = int(r["input_tokens"])
            row_dict["output_tokens"] = int(r["output_tokens"])
            row_dict["cache_creation_tokens"] = int(r.get("cache_creation_tokens") or 0)
            row_dict["cache_read_tokens"] = int(r.get("cache_read_tokens") or 0)
            row_dict["percentage_share"] = pct
            row_dict["estimated_cost"] = round(float(row_dict["estimated_cost"]), 4)
            if "client_ip" in row_dict and not row_dict.get("client_alias"):
                ip = row_dict["client_ip"]
                if ip and hasattr(self, "resolve_client_alias"):
                    row_dict["client_alias"] = self.resolve_client_alias(ip)  # type: ignore[attr-defined]
            rows.append(row_dict)

        totals = {
            "total_tokens": total_tok,
            "input_tokens": sum(int(r["input_tokens"]) for r in raw_rows),
            "output_tokens": sum(int(r["output_tokens"]) for r in raw_rows),
            "cache_creation_tokens": sum(int(r.get("cache_creation_tokens") or 0) for r in raw_rows),
            "cache_read_tokens": sum(int(r.get("cache_read_tokens") or 0) for r in raw_rows),
            "estimated_cost": round(sum(float(r["estimated_cost"]) for r in raw_rows), 4),
            "request_count": sum(int(r["request_count"]) for r in raw_rows),
        }

        return {
            "success": True,
            "dimensions": dim_list,
            "window": window,
            "rows": rows,
            "totals": totals,
        }

    get_multi_dimensional_pivot = get_pivot_metrics

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
        limit: int = 500,
        source: Optional[str] = None,
        instance_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_dir: str = "desc",
    ) -> Dict[str, Any]:
        """
        Executes multi-dimensional historical analytics across time periods and operational dimensions.
        Supports hourly, daily, weekly, monthly, and yearly time slices, client alias resolution,
        and cross-platform tag (`group`) pivoting.
        """
        gb_norm = (group_by or "day").strip().lower()
        if gb_norm in ("hour", "hourly"):
            time_expr = "strftime('%Y-%m-%d %H:00', recorded_at)"
            group_by = "hour"
        elif gb_norm in ("week", "weekly"):
            time_expr = "strftime('%Y-W%W', recorded_at)"
            group_by = "week"
        elif gb_norm in ("month", "monthly"):
            time_expr = "strftime('%Y-%m', recorded_at)"
            group_by = "month"
        elif gb_norm in ("year", "yearly"):
            time_expr = "strftime('%Y', recorded_at)"
            group_by = "year"
        else:
            time_expr = "strftime('%Y-%m-%d', recorded_at)"
            group_by = "day"

        conditions = ["1=1"]
        params: List[Any] = []

        if start_date:
            conditions.append("recorded_at >= ?")
            params.append(start_date)
        if end_date:
            # If date-only YYYY-MM-DD is supplied, include the full end day up to 23:59:59
            end_val = f"{end_date}T23:59:59" if len(str(end_date).strip()) == 10 else str(end_date)
            conditions.append("recorded_at <= ?")
            params.append(end_val)
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
        if source:
            conditions.append("source = ?")
            params.append(source.lower())
        if instance_id:
            conditions.append("instance_id = ?")
            params.append(instance_id)
        if client_ip:
            conditions.append("(client_ip = ? OR client_alias = ?)")
            params.extend([client_ip, client_ip])

        where_clause = " AND ".join(conditions)

        valid_dims = {
            "provider",
            "account_id",
            "team_name",
            "user_name",
            "model",
            "project_id",
            "token_id",
            "source",
            "instance_id",
            "client_ip",
            "client_alias",
        }
        is_tag_dim = dimension in ("group", "tag")
        dim_col = dimension if dimension in valid_dims else None

        if dim_col:
            select_group = (
                f"{time_expr} AS period, {dim_col} AS dimension_value, provider, "
                f"MAX(account_id) AS account_id, MAX(team_name) AS team_name, MAX(user_name) AS user_name, "
                f"MAX(model) AS model, MAX(source) AS source, MAX(instance_id) AS instance_id, "
                f"MAX(client_ip) AS client_ip, MAX(client_alias) AS client_alias, MAX(project_id) AS project_id, "
                f"MAX(token_id) AS token_id"
            )
            group_by_clause = f"GROUP BY {time_expr}, {dim_col}, provider ORDER BY period ASC, total_tokens DESC"
        else:
            select_group = (
                f"{time_expr} AS period, provider, account_id, team_name, user_name, model, "
                f"COALESCE(source, 'direct') AS source, COALESCE(instance_id, 'local-default') AS instance_id, "
                f"COALESCE(client_ip, '127.0.0.1') AS client_ip, client_alias, project_id, token_id"
            )
            group_by_clause = (
                f"GROUP BY {time_expr}, provider, account_id, team_name, user_name, model, "
                f"COALESCE(source, 'direct'), COALESCE(instance_id, 'local-default'), COALESCE(client_ip, '127.0.0.1'), project_id, token_id "
                f"ORDER BY period ASC"
            )

        query_sql = f"""
            SELECT
                {select_group},
                SUM(input_tokens) AS input_tokens,
                SUM(output_tokens) AS output_tokens,
                SUM(COALESCE(cache_creation_tokens, 0)) AS cache_creation_tokens,
                SUM(COALESCE(cache_read_tokens, 0)) AS cache_read_tokens,
                SUM(total_tokens) AS total_tokens,
                SUM(estimated_cost) AS total_cost_usd,
                SUM(request_count) AS request_count,
                COUNT(id) AS event_count,
                COUNT(DISTINCT session_id) AS session_count
            FROM usage_events
            WHERE {where_clause}
            {group_by_clause}
            LIMIT ?
        """
        params.append(limit)

        with self._lock:  # type: ignore[attr-defined]
            conn = self._get_connection()  # type: ignore[attr-defined]
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT id, name, endpoint, engine, compute_group FROM managed_nodes")
                nodes_map = {r["id"]: dict(r) for r in cursor.fetchall()}
                cursor.execute(query_sql, params)
                rows = cursor.fetchall()
            finally:
                conn.close()

        tags = (
            self.get_cross_platform_tags()  # type: ignore[attr-defined]
            if (is_tag_dim and hasattr(self, "get_cross_platform_tags"))
            else []
        )

        records: List[Dict[str, Any]] = []
        tot_tok = 0
        tot_in = 0
        tot_out = 0
        tot_cache_create = 0
        tot_cache_read = 0
        tot_cost = 0.0
        tot_savings = 0.0
        tot_events = 0
        FRONTIER_RATE_PER_M = 6.00

        for r in rows:
            d = dict(r)
            d["total_cost_usd"] = round(float(d.get("total_cost_usd") or 0.0), 4)
            d["avg_latency_ms"] = round(float(d.get("avg_latency_ms") or 0.0), 1)

            # Resolve client_alias fallback when client_ip is present
            c_ip = d.get("client_ip") or "127.0.0.1"
            d["client_ip"] = c_ip
            if c_ip and not d.get("client_alias") and hasattr(self, "resolve_client_alias"):
                d["client_alias"] = self.resolve_client_alias(c_ip)  # type: ignore[attr-defined]
            if not d.get("client_alias"):
                d["client_alias"] = "Localhost" if c_ip in ("127.0.0.1", "::1", "localhost") else c_ip

            d["source"] = d.get("source") or "direct"
            d["instance_id"] = d.get("instance_id") or "local-default"

            # Enrich with Canonical 8-Tier Telemetry Taxonomy fields
            tax = normalize_event_taxonomy(d, nodes_map=nodes_map)
            d["locality"] = tax["locality"]
            d["locality_label"] = tax["locality_label"]
            d["account_tier"] = tax["account_tier"]
            d["account_tier_label"] = tax["account_tier_label"]
            d["tenant_account"] = tax["tenant_account"]
            d["workspace_pool"] = tax["workspace_pool"]
            d["principal_seat"] = tax["principal_seat"]
            d["compute_node"] = tax["compute_node"]
            d["client_host"] = tax["client_host"]
            d["access_route_label"] = tax["access_route_label"]

            if dim_col == "client_alias" and not d.get("dimension_value"):
                d["dimension_value"] = d.get("client_alias") or c_ip or "Localhost"
            elif dimension == "locality":
                d["dimension_value"] = tax["locality_label"]
            elif dimension == "account_tier":
                d["dimension_value"] = tax["account_tier_label"]
            elif dimension == "compute_node":
                d["dimension_value"] = tax["compute_node"]

            if is_tag_dim:
                tag_val = self._match_cross_platform_tag(d, tags)
                d["dimension_value"] = tag_val
                group_key = tag_val
            else:
                group_key = (
                    d.get("dimension_value")
                    or d.get("account_id")
                    or d.get("team_name")
                    or d.get("user_name")
                    or d.get("provider")
                    or "All"
                )
            d["group_key"] = group_key
            d["estimated_cost"] = d["total_cost_usd"]
            d["input_tokens"] = int(d.get("input_tokens") or 0)
            d["output_tokens"] = int(d.get("output_tokens") or 0)
            d["cache_creation_tokens"] = int(d.get("cache_creation_tokens") or 0)
            d["cache_read_tokens"] = int(d.get("cache_read_tokens") or 0)
            d["total_tokens"] = int(d.get("total_tokens") or 0)
            d["event_count"] = int(d.get("event_count") or 0)
            d["session_count"] = int(d.get("session_count") or 0)

            prov_lower = str(d.get("provider") or "").strip().lower()
            is_local = prov_lower in ("ollama", "lmstudio", "vllm", "oobabooga", "tabby_kobold", "local")
            d["is_local_model"] = is_local
            if is_local and d["total_cost_usd"] == 0.0:
                savings_usd = round((d["total_tokens"] / 1_000_000.0) * FRONTIER_RATE_PER_M, 4)
                d["estimated_savings_usd"] = savings_usd
                d["net_cost_usd"] = -savings_usd
            else:
                d["estimated_savings_usd"] = 0.0
                d["net_cost_usd"] = d["total_cost_usd"]

            tot_tok += d["total_tokens"]
            tot_in += d["input_tokens"]
            tot_out += d["output_tokens"]
            tot_cache_create += d["cache_creation_tokens"]
            tot_cache_read += d["cache_read_tokens"]
            tot_cost += float(d.get("total_cost_usd") or 0.0)
            tot_savings += float(d.get("estimated_savings_usd") or 0.0)
            tot_events += d["event_count"]
            records.append(d)

        if sort_by:
            reverse = str(sort_dir or "desc").lower() == "desc"
            records.sort(key=lambda item: item.get(sort_by) or 0, reverse=reverse)

        summary = {
            "total_tokens": tot_tok,
            "input_tokens": tot_in,
            "output_tokens": tot_out,
            "cache_creation_tokens": tot_cache_create,
            "cache_read_tokens": tot_cache_read,
            "total_estimated_cost": round(tot_cost, 4),
            "total_cost_usd": round(tot_cost, 4),
            "total_estimated_savings_usd": round(tot_savings, 4),
            "net_cost_usd": round(tot_cost - tot_savings, 4),
            "total_events": tot_events,
            "distinct_dimensions": len(set(r.get("group_key") for r in records)),
        }

        return {
            "group_by": group_by,
            "dimension": "group" if is_tag_dim else dim_col,
            "filters": {
                "start_date": start_date,
                "end_date": end_date,
                "provider": provider,
                "account_id": account_id,
                "team_name": team_name,
                "user_name": user_name,
                "token_id": token_id,
                "model": model,
                "project_id": project_id,
                "source": source,
                "instance_id": instance_id,
                "client_ip": client_ip,
            },
            "record_count": len(records),
            "totals": summary,
            "summary": summary,
            "records": records,
            "rows": records,
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
        model: Optional[str] = None,
        token_id: Optional[str] = None,
        project_id: Optional[str] = None,
        dimension: Optional[str] = None,
        source: Optional[str] = None,
        instance_id: Optional[str] = None,
        client_ip: Optional[str] = None,
    ) -> str:
        """
        Exports historical report as an RFC-4180 compliant CSV string with full v2.0
        filter parity and multi-instance / client attribution columns.
        """
        report = self.query_historical_report(
            group_by=group_by,
            start_date=start_date,
            end_date=end_date,
            provider=provider,
            account_id=account_id,
            team_name=team_name,
            user_name=user_name,
            token_id=token_id,
            model=model,
            project_id=project_id,
            dimension=dimension,
            source=source,
            instance_id=instance_id,
            client_ip=client_ip,
            limit=5000,
        )
        lines = [
            "Period,Provider,Account,Team,User,Model,Source,Instance,Client IP,Client Alias,Dimension Key,Input Tokens,Output Tokens,Cache Create Tokens,Cache Read Tokens,Total Tokens,Total Cost (USD),Sessions,Events"
        ]
        for r in report.get("records", []):
            period = str(r.get("period") or "").replace('"', '""')
            prov = str(r.get("provider") or "").replace('"', '""')
            acct = str(r.get("account_id") or "").replace('"', '""')
            team = str(r.get("team_name") or "").replace('"', '""')
            user = str(r.get("user_name") or "").replace('"', '""')
            mdl = str(r.get("model") or "").replace('"', '""')
            src = str(r.get("source") or "direct").replace('"', '""')
            inst = str(r.get("instance_id") or "local-default").replace('"', '""')
            cip = str(r.get("client_ip") or "127.0.0.1").replace('"', '""')
            calias = str(r.get("client_alias") or "").replace('"', '""')
            gkey = str(r.get("group_key") or "").replace('"', '""')
            in_t = int(r.get("input_tokens") or 0)
            out_t = int(r.get("output_tokens") or 0)
            cc_t = int(r.get("cache_creation_tokens") or 0)
            cr_t = int(r.get("cache_read_tokens") or 0)
            tot_t = int(r.get("total_tokens") or 0)
            cost = float(r.get("total_cost_usd") or 0.0)
            sess = int(r.get("session_count") or 0)
            evt = int(r.get("event_count") or 0)
            lines.append(
                f'"{period}","{prov}","{acct}","{team}","{user}","{mdl}","{src}","{inst}","{cip}","{calias}","{gkey}",{in_t},{out_t},{cc_t},{cr_t},{tot_t},{cost:.4f},{sess},{evt}'
            )

        return "\r\n".join(lines)

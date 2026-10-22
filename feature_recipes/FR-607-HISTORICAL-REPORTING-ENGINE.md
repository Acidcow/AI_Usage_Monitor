# Feature Recipe: FR-607 - Historical Reporting & Multi-Dimensional Analytics Engine

**Ticket ID**: `AIUM-607`  
**Epic**: `EPIC-CORE-TELEMETRY`  
**Status**: Done  
**Standard**: ASD-STE100 Simplified Technical English  

---

## 1. Purpose

This recipe defines the historical reporting engine (`query_historical_report`), CSV export pipeline (`export_historical_csv`), and multi-dimensional pivot table engine (`get_multi_dimensional_pivot`) for AI Usage Monitor.

## 2. Requirements

1. Support time-series bucketing by `hourly`, `daily`, `weekly`, `monthly`, and `yearly` intervals.
2. Support grouping and filtering across `provider`, `account_id`, `model`, `source`, `instance_id`, `client_ip`, `token_id`, `project_id`, `user_name`, `team_name`, `department`, and cross-platform `group` tags.
3. Compute summary KPIs (`total_requests`, `total_input_tokens`, `total_output_tokens`, `total_cache_tokens`, `total_tokens`, `total_cost_usd`, `avg_latency_ms`), time-bucketed stacked chart series, dimension breakdowns, and sortable tabular records.
4. Provide RFC-4180 compliant CSV export with full filter parity.

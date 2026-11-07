"""
AI Usage Monitor - Multi-Model Execution Planner & Subagent Orchestrator
========================================================================
Zero-dependency CLI tool to plan, scope, route to optimal model tiers
(flash_lite, flash, pro), generate bounded subagent prompts, and run
selective verification for the v2.5 Platform Overhaul.

Usage:
  python dev_tools/orchestrate_v2_overhaul.py init-plan
  python dev_tools/orchestrate_v2_overhaul.py plan [--wave N] [--model TIER]
  python dev_tools/orchestrate_v2_overhaul.py prompt AIUM-1001 [--json]
  python dev_tools/orchestrate_v2_overhaul.py verify AIUM-1001
"""

import argparse
import datetime
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DB_PATH = str(REPO_ROOT / "dev_roadmap.db")

EPIC_SPEC = {
    "id": "EPIC-V2.5-UNIFIED-OVERHAUL",
    "title": "v2.5 Unified Core, Bulletproof Telemetry, Hybrid AI Niche Capabilities & Ultra-Modern Theme Engine",
    "description": (
        "Consolidate duplicate code across Full Web UI, Web Mini Widget, and Native Taskbar Widget; "
        "harden SQLite WAL concurrency, connection lifecycle, and zero double-accounting; "
        "remove synthetic/hardcoded remnants; introduce 6 selectable ultra-modern themes; "
        "and deliver high-leverage hybrid AI niche capabilities."
    ),
    "status": "In Progress",
}

# Carefully scoped tickets with explicit model tier routing to minimize token burn:
# - flash_lite : Deterministic bug fixes, dead-code/constant cleanup, schema pragma/index additions.
# - flash      : Focused module extraction, UI component synchronization, theme CSS/API wiring.
# - pro        : Complex cross-cutting architectural refactoring, deduplication correlation, predictive math.
OVERHAUL_TICKETS: List[Dict[str, Any]] = [
    {
        "id": "AIUM-1001",
        "wave": 1,
        "model_tier": "flash_lite",
        "role": "SQLite WAL & Connection Guard Engineer",
        "title": "SQLite WAL Mode, Context-Managed Connections & Composite Indexing",
        "priority": "Critical",
        "ticket_type": "Bug",
        "recipe_file": "feature_recipes/FR-1001-SQLITE-WAL-AND-INDEXES.md",
        "estimated_tokens": 12000,
        "context_files": [
            "backend/storage/database.py",
            "backend/storage/reporting_engine.py",
        ],
        "scope_boundaries": (
            "1. Enable PRAGMA journal_mode=WAL, PRAGMA synchronous=NORMAL, PRAGMA busy_timeout=5000, "
            "and PRAGMA foreign_keys=ON in _get_connection(). "
            "2. Add context manager self.connection() ensuring conn.close() in finally blocks across all methods. "
            "3. Collapse redundant ALTER TABLE migrations in _init_schema(). "
            "4. Add composite indexes idx_usage_dedup(provider, session_id, total_tokens), "
            "idx_usage_external(provider, external_id), and idx_usage_prov_time(provider, recorded_at). "
            "5. Consolidate record_usage_event() from 7 sequential connection opens into 1 atomic transaction."
        ),
        "test_module": "tests/test_sqlite_wal_and_connection_guards.py",
    },
    {
        "id": "AIUM-1002",
        "wave": 1,
        "model_tier": "flash_lite",
        "role": "Runtime Sanitization & Bug Fixer",
        "title": "Eliminate Hardcoded Identities, UnboundLocalError Bug, Paid API Pings & Thread Leaks",
        "priority": "Critical",
        "ticket_type": "Bug",
        "recipe_file": "feature_recipes/FR-1002-RUNTIME-SANITIZATION-AND-BUGFIXES.md",
        "estimated_tokens": 15000,
        "context_files": [
            "backend/providers/claude.py",
            "backend/security/dpapi_vault.py",
            "backend/discovery/p2p_tunnel.py",
            "frontend/js/app.js",
            "backend/tray/native_widget.py",
        ],
        "scope_boundaries": (
            "1. Fix UnboundLocalError on jsonl_files in claude.py:scan_local_logs when ~/.claude is absent. "
            "2. Remove live paid POST /v1/messages 'ping' probe from 10s background loop in claude.py. "
            "3. Add threading.RLock() and atomic temp-file-rename write to DPAPIVault._save_store(). "
            "4. Remove duplicate switchTab() declaration in frontend/js/app.js (merge L3737 & L4249) and duplicate "
            "flyout label config in native_widget.py (L1348). "
            "5. Replace hardcoded personal names/emails with dynamic OS username/profile lookups."
        ),
        "test_module": "tests/test_runtime_sanitization_and_bugfixes.py",
    },
    {
        "id": "AIUM-1003",
        "wave": 1,
        "model_tier": "flash",
        "role": "Log Scanner & Polling Optimizer",
        "title": "Incremental File Offset/mtime Log Scanning & Adaptive Polling Cadence",
        "priority": "High",
        "ticket_type": "Task",
        "recipe_file": "feature_recipes/FR-1003-INCREMENTAL-SCANNER-AND-POLLING.md",
        "estimated_tokens": 18000,
        "context_files": [
            "run_monitor.py",
            "backend/providers/claude.py",
            "backend/providers/ollama.py",
            "backend/tray/native_widget.py",
        ],
        "scope_boundaries": (
            "1. Track file mtime and byte offsets for Claude JSONL/LevelDB and Ollama server.log so 10s syncs only "
            "parse newly appended bytes instead of re-reading entire directories. "
            "2. Align native_widget.py polling loop with ui_refresh_interval_seconds instead of hardcoded 2000ms. "
            "3. Remove synthetic waveform multipliers ([0.7, 0.9, 1.1...]) from widget.js and native_widget.py, "
            "rendering honest zero-activity baselines when idle."
        ),
        "test_module": "tests/test_incremental_scanner_and_polling.py",
    },
    {
        "id": "AIUM-1004",
        "wave": 2,
        "model_tier": "pro",
        "role": "Telemetry Deduplication Architect",
        "title": "Bulletproof Zero Double-Accounting Across Proxies, Governor & Local Scanners",
        "priority": "Critical",
        "ticket_type": "Feature",
        "recipe_file": "feature_recipes/FR-1004-ZERO-DOUBLE-ACCOUNTING-V2.md",
        "estimated_tokens": 28000,
        "context_files": [
            "backend/proxy/transparent_proxy.py",
            "backend/discovery/traffic_governor.py",
            "backend/providers/claude.py",
            "backend/providers/ollama.py",
            "backend/storage/database.py",
        ],
        "scope_boundaries": (
            "1. Extract upstream Anthropic message.id / request-id in transparent_proxy.py (SSE & JSON) and pass "
            "as external_id to claude_provider.ingest_proxy_interaction and record_usage_event. "
            "2. Generate deterministic content/window fingerprints for Ollama requests in traffic_governor.py and "
            "ollama.py:scan_local_logs so proxied/governed local inference is never double-counted. "
            "3. Enhance temporal correlation in record_usage_event to match (provider, model, input_tokens, "
            "output_tokens) within a +-15s window across proxy and scanner sources."
        ),
        "test_module": "tests/test_zero_double_accounting_v2.py",
    },
    {
        "id": "AIUM-1005",
        "wave": 2,
        "model_tier": "flash",
        "role": "Pricing & Canonical Contracts Engineer",
        "title": "Canonical Data Contracts (backend/contracts/) & Model-Specific Pricing Matrix",
        "priority": "High",
        "ticket_type": "Feature",
        "recipe_file": "feature_recipes/FR-1005-CANONICAL-CONTRACTS-AND-PRICING.md",
        "estimated_tokens": 22000,
        "context_files": [
            "backend/contracts/models.py",
            "backend/contracts/pricing.py",
            "backend/storage/database.py",
            "backend/providers/claude.py",
            "backend/providers/gemini.py",
            "backend/storage/reporting_engine.py",
        ],
        "scope_boundaries": (
            "1. Create backend/contracts/models.py defining canonical dataclasses: UsageEvent, ProviderSnapshot, "
            "TelemetrySeries, TelemetrySeriesPoint, ThemeConfig, WidgetConfig. "
            "2. Create backend/contracts/pricing.py with a single canonical pricing table covering Claude (Opus, "
            "Sonnet, Haiku), Gemini (2.5 Pro, 2.5 Flash, 1.5), OpenAI (GPT-4o, 4o-mini, o1/o3), and Ollama local "
            "savings weights, including prompt cache write (1.25x) and cache read (0.1x) tiers. "
            "3. Remove all 4 duplicate cost formulas in claude.py, gemini.py, database.py, and reporting_engine.py."
        ),
        "test_module": "tests/test_canonical_contracts_and_pricing.py",
    },
    {
        "id": "AIUM-1006",
        "wave": 2,
        "model_tier": "pro",
        "role": "Time-Series SQL Consolidation Architect",
        "title": "Unify get_granular_timeseries & get_hierarchical_trends with SQL Bucketing",
        "priority": "High",
        "ticket_type": "Task",
        "recipe_file": "feature_recipes/FR-1006-UNIFIED-TIMESERIES-ENGINE.md",
        "estimated_tokens": 30000,
        "context_files": [
            "backend/storage/database.py",
            "backend/storage/timeseries_engine.py",
            "backend/server/http_server.py",
        ],
        "scope_boundaries": (
            "1. Extract the 870+ lines of duplicate time-series bucketing from database.py into a clean mixin "
            "backend/storage/timeseries_engine.py. "
            "2. Push time-bucket grouping into SQLite queries where possible to avoid loading 100k+ raw rows into "
            "Python memory on 3m/6m/12m windows. "
            "3. Ensure both /api/usage/timeseries and /api/usage/trends/hierarchy return canonical ISO-8601 UTC "
            "keys paired with workstation local labels."
        ),
        "test_module": "tests/test_unified_timeseries_engine.py",
    },
    {
        "id": "AIUM-1007",
        "wave": 3,
        "model_tier": "flash",
        "role": "Shared Frontend Core Engineer",
        "title": "Extract Shared Frontend Core (frontend/js/core/) for Full Web UI & Mini Widget",
        "priority": "Critical",
        "ticket_type": "Feature",
        "recipe_file": "feature_recipes/FR-1007-SHARED-FRONTEND-CORE.md",
        "estimated_tokens": 25000,
        "context_files": [
            "frontend/js/core/formatters.js",
            "frontend/js/core/api_client.js",
            "frontend/js/core/chart_renderer.js",
            "frontend/js/core/telemetry_hierarchy.js",
            "frontend/index.html",
            "frontend/mini_widget.html",
            "frontend/js/widget.js",
            "frontend/js/app.js",
        ],
        "scope_boundaries": (
            "1. Create frontend/js/core/formatters.js (tokens, currency, local time, countdowns, HTML escaping). "
            "2. Create frontend/js/core/api_client.js (shared fetch wrapper, settings sync, icon sync). "
            "3. Create frontend/js/core/chart_renderer.js (unified SVG chart & sparkline generator with crisp "
            "vector-effect='non-scaling-stroke', honest idle baselines, and crosshair tooltips). "
            "4. Create frontend/js/core/telemetry_hierarchy.js (shared child series extractor). "
            "5. Wire both index.html/app.js and mini_widget.html/widget.js to consume frontend/js/core/*, "
            "deleting duplicate functions and adding Granularity & Scope selectors to the Mini Widget."
        ),
        "test_module": "tests/test_shared_frontend_core.py",
    },
    {
        "id": "AIUM-1008",
        "wave": 3,
        "model_tier": "flash",
        "role": "Design Systems & Theme Engineer",
        "title": "6 Ultra-Modern Selectable Themes & Layout Density Engine Across Web UI & Widgets",
        "priority": "High",
        "ticket_type": "Feature",
        "recipe_file": "feature_recipes/FR-1008-ULTRA-MODERN-THEME-ENGINE.md",
        "estimated_tokens": 24000,
        "context_files": [
            "backend/contracts/themes.py",
            "backend/server/http_server.py",
            "frontend/css/themes.css",
            "frontend/css/styles.css",
            "frontend/css/widget.css",
            "frontend/mini_widget.html",
            "backend/tray/native_widget.py",
        ],
        "scope_boundaries": (
            "1. Implement 6 selectable ultra-modern themes in backend/contracts/themes.py & frontend/css/themes.css: "
            "Linear Obsidian, Vercel Geist Monochrome, Cyberpunk Neo-HUD, Catppuccin Mocha, Tokyo Night Storm, and "
            "Executive Paper (High-Contrast Daylight). "
            "2. Expose GET /api/themes so Full Web UI, mini_widget.html, and native_widget.py share one palette source. "
            "3. Extract inline styles from mini_widget.html into frontend/css/widget.css and replace hardcoded hex "
            "overrides in app.js with semantic CSS variables (--bg-canvas, --bg-surface, --accent-primary, etc.). "
            "4. Fix WCAG AA contrast ratios (minimum 4.5:1) and enforce >=10px legible typography on HiDPI displays. "
            "5. Sync app icon/mascot selection via /api/settings across Web UI, Mini Widget, and Windows Tray."
        ),
        "test_module": "tests/test_ultra_modern_theme_engine.py",
    },
    {
        "id": "AIUM-1009",
        "wave": 4,
        "model_tier": "flash",
        "role": "Prompt Cache & Session UX Engineer",
        "title": "Prompt Cache Efficiency Analytics, TTL Keep-Alive Timer & Session Cache Columns",
        "priority": "High",
        "ticket_type": "Feature",
        "recipe_file": "feature_recipes/FR-1009-PROMPT-CACHE-EFFICIENCY-ANALYTICS.md",
        "estimated_tokens": 20000,
        "context_files": [
            "backend/analytics/cache_analyzer.py",
            "frontend/components/session_timeline.html",
            "frontend/components/usage_gauge_card.html",
            "frontend/js/app.js",
        ],
        "scope_boundaries": (
            "1. Add Cache Read, Cache Write, and Cache Hit % columns to Recent Agentic Sessions & Tokens table "
            "(resolving the Input 2 + Output 684 vs 724k Total confusion). "
            "2. Compute Prompt Cache Reusability Score (Reads vs Writes) and net dollar savings/penalties against "
            "Anthropic 1.25x write / 0.1x read rates. "
            "3. Add a 5-minute Anthropic Prompt Cache TTL warmth indicator showing when the active session cache is "
            "warm vs expiring, plus accurate multi-turn session duration calculation."
        ),
        "test_module": "tests/test_prompt_cache_efficiency_analytics.py",
    },
    {
        "id": "AIUM-1010",
        "wave": 4,
        "model_tier": "pro",
        "role": "Quota Pacing & Context Bloat Architect",
        "title": "Rolling 5h/7d Burn-Rate Pacing Forecaster, Cross-Tab Quota Alignment & Bloat Detector",
        "priority": "High",
        "ticket_type": "Feature",
        "recipe_file": "feature_recipes/FR-1010-QUOTA-PACING-AND-BLOAT-DETECTOR.md",
        "estimated_tokens": 26000,
        "context_files": [
            "backend/analytics/throughput_engine.py",
            "backend/storage/database.py",
            "frontend/components/capacity_analytics.html",
            "frontend/js/app.js",
        ],
        "scope_boundaries": (
            "1. Unify Session Remaining % and Weekly Pool % between Dashboard and Capacity & Velocity tabs. "
            "2. Build Rolling-Window Burn-Rate Pacing Forecaster: compare time-to-exhaustion against 5h/7d reset "
            "countdowns and display actionable pacing guidance (Sustainable / Warning / Impending Lockout). "
            "3. Implement Context-Window Bloat & Agent Loop Detector: flag sessions where input tokens grow >40% "
            "consecutively across >=4 turns with minimal output growth."
        ),
        "test_module": "tests/test_quota_pacing_and_bloat_detector.py",
    },
    {
        "id": "AIUM-1011",
        "wave": 4,
        "model_tier": "flash",
        "role": "Benchmark & Guardrails Engineer",
        "title": "Live Ollama/Cloud Benchmark Execution, Transcript Inspection Modal & Budget Breakers",
        "priority": "Medium",
        "ticket_type": "Feature",
        "recipe_file": "feature_recipes/FR-1011-LIVE-BENCHMARKS-AND-CIRCUIT-BREAKERS.md",
        "estimated_tokens": 22000,
        "context_files": [
            "backend/analytics/benchmark_engine.py",
            "backend/proxy/transparent_proxy.py",
            "frontend/components/benchmark_scorecard.html",
            "frontend/js/app.js",
        ],
        "scope_boundaries": (
            "1. Upgrade benchmark_engine.py to execute real live inference against local Ollama / configured providers "
            "(with deterministic mock fallback only in unit test mode) and record real TTFT, tok/s, and outputs. "
            "2. Add an interactive Evaluation Run Inspection Modal in the UI to view prompts, model outputs, AST "
            "errors, and prompt injection test transcripts. "
            "3. Add configurable per-session / hourly budget circuit breakers in transparent_proxy.py with optional "
            "automatic spillover routing to healthy LAN Ollama worker nodes when cloud quota crosses 85% or hits 429."
        ),
        "test_module": "tests/test_live_benchmarks_and_circuit_breakers.py",
    },
    {
        "id": "AIUM-1012",
        "wave": 5,
        "model_tier": "flash_lite",
        "role": "UX Polish & Diagnostics Engineer",
        "title": "Troubleshooting Log Deduplication/Search, Report Date Presets & Provider Status Polish",
        "priority": "Medium",
        "ticket_type": "Task",
        "recipe_file": "feature_recipes/FR-1012-UX-POLISH-AND-LOG-DEDUP.md",
        "estimated_tokens": 14000,
        "context_files": [
            "frontend/components/troubleshooter_panel.html",
            "frontend/components/reports_panel.html",
            "frontend/components/provider_hub.html",
            "frontend/js/app.js",
            "frontend/css/styles.css",
        ],
        "scope_boundaries": (
            "1. Add duplicate error collapsing (e.g. 'x42') and real-time search/category filtering to the "
            "Troubleshooting panel. "
            "2. Add quick date preset pills (Today, Yesterday, Last 24h, 7d, 30d, MTD, All-Time) and sticky table "
            "headers to Historical Reports. "
            "3. Change unconfigured OpenAI/ChatGPT badge from alarming red 'ERROR' to neutral 'NOT CONFIGURED', "
            "and fix LAN discovery default CIDR from /32 to /24 when auto-detecting subnets."
        ),
        "test_module": "tests/test_ux_polish_and_log_dedup.py",
    },
]


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_orchestration_schema() -> None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_execution_meta (
                ticket_id TEXT PRIMARY KEY,
                wave INTEGER NOT NULL,
                model_tier TEXT NOT NULL,
                role TEXT NOT NULL,
                estimated_tokens INTEGER NOT NULL,
                context_files_json TEXT NOT NULL,
                scope_boundaries TEXT NOT NULL,
                test_module TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def init_plan() -> None:
    ensure_orchestration_schema()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM epics WHERE id = ?", (EPIC_SPEC["id"],))
        if cur.fetchone()[0] == 0:
            cur.execute(
                """
                INSERT INTO epics (id, title, description, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    EPIC_SPEC["id"],
                    EPIC_SPEC["title"],
                    EPIC_SPEC["description"],
                    EPIC_SPEC["status"],
                    now,
                    now,
                ),
            )
        else:
            cur.execute(
                "UPDATE epics SET title = ?, description = ?, updated_at = ? WHERE id = ?",
                (EPIC_SPEC["title"], EPIC_SPEC["description"], now, EPIC_SPEC["id"]),
            )

        for t in OVERHAUL_TICKETS:
            cur.execute("SELECT COUNT(*) FROM tickets WHERE id = ?", (t["id"],))
            if cur.fetchone()[0] == 0:
                cur.execute(
                    """
                    INSERT INTO tickets (id, epic_id, title, description, ticket_type, status, priority, recipe_file, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'Todo', ?, ?, ?, ?)
                    """,
                    (
                        t["id"],
                        EPIC_SPEC["id"],
                        t["title"],
                        t["scope_boundaries"],
                        t["ticket_type"],
                        t["priority"],
                        t["recipe_file"],
                        now,
                        now,
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE tickets
                    SET epic_id = ?, title = ?, description = ?, ticket_type = ?, priority = ?, recipe_file = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        EPIC_SPEC["id"],
                        t["title"],
                        t["scope_boundaries"],
                        t["ticket_type"],
                        t["priority"],
                        t["recipe_file"],
                        now,
                        t["id"],
                    ),
                )

            cur.execute(
                """
                INSERT OR REPLACE INTO ticket_execution_meta
                (ticket_id, wave, model_tier, role, estimated_tokens, context_files_json, scope_boundaries, test_module, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    t["id"],
                    t["wave"],
                    t["model_tier"],
                    t["role"],
                    t["estimated_tokens"],
                    json.dumps(t["context_files"]),
                    t["scope_boundaries"],
                    t["test_module"],
                    now,
                ),
            )
        conn.commit()
        print(f"[OK] Seeded Epic '{EPIC_SPEC['id']}' and {len(OVERHAUL_TICKETS)} model-routed tickets into dev_roadmap.db.")
    finally:
        conn.close()


def print_plan(wave_filter: Optional[int] = None, model_filter: Optional[str] = None) -> None:
    ensure_orchestration_schema()
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        query = """
            SELECT t.id, t.title, t.status, t.priority, m.wave, m.model_tier, m.role,
                   m.estimated_tokens, m.context_files_json, m.test_module
            FROM tickets t
            JOIN ticket_execution_meta m ON t.id = m.ticket_id
            WHERE 1=1
        """
        params: List[Any] = []
        if wave_filter is not None:
            query += " AND m.wave = ?"
            params.append(wave_filter)
        if model_filter:
            query += " AND m.model_tier = ?"
            params.append(model_filter)
        query += " ORDER BY m.wave ASC, t.id ASC"
        rows = cur.execute(query, params).fetchall()
    finally:
        conn.close()

    if not rows:
        print("No tickets found. Run `python dev_tools/orchestrate_v2_overhaul.py init-plan` first.")
        return

    print("\n" + "=" * 96)
    print("AI USAGE MONITOR v2.5 - MULTI-MODEL ORCHESTRATION & EXECUTION PLAN")
    print("=" * 96)

    total_est = 0
    by_tier: Dict[str, int] = {"flash_lite": 0, "flash": 0, "pro": 0}
    current_wave = None

    for r in rows:
        if r["wave"] != current_wave:
            current_wave = r["wave"]
            print(f"\n--- WAVE {current_wave} " + "-" * 83)
        est = int(r["estimated_tokens"])
        total_est += est
        tier = r["model_tier"]
        by_tier[tier] = by_tier.get(tier, 0) + est
        ctx_files = json.loads(r["context_files_json"])
        print(
            f"  [{r['id']}] ({r['status']:<11}) | Model: {tier:<10} | Priority: {r['priority']:<8} | Est: ~{est // 1000}k tok"
        )
        print(f"    Title   : {r['title']}")
        print(f"    Role    : {r['role']}")
        print(f"    Context : {', '.join(ctx_files)}")
        print(f"    Verify  : python dev_tools/orchestrate_v2_overhaul.py verify {r['id']}")

    unoptimized_pro_tokens = len(rows) * 65000
    savings_pct = round((1.0 - (total_est / max(1, unoptimized_pro_tokens))) * 100, 1)
    print("\n" + "=" * 96)
    print(
        f"TOKEN BUDGET SUMMARY: Total Estimated = ~{total_est // 1000}k tokens "
        f"(vs ~{unoptimized_pro_tokens // 1000}k un-scoped Pro baseline -> ~{savings_pct}% savings)"
    )
    print(
        f"  flash_lite: ~{by_tier.get('flash_lite', 0) // 1000}k tok | "
        f"flash: ~{by_tier.get('flash', 0) // 1000}k tok | "
        f"pro: ~{by_tier.get('pro', 0) // 1000}k tok"
    )
    print("=" * 96 + "\n")


def generate_subagent_prompt(ticket_id: str, as_json: bool = False) -> None:
    ensure_orchestration_schema()
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        row = cur.execute(
            """
            SELECT t.id, t.title, t.priority, t.recipe_file, m.wave, m.model_tier,
                   m.role, m.context_files_json, m.scope_boundaries, m.test_module
            FROM tickets t
            JOIN ticket_execution_meta m ON t.id = m.ticket_id
            WHERE t.id = ?
            """,
            (ticket_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        print(f"[ERROR] Ticket '{ticket_id}' not found in execution plan.")
        sys.exit(1)

    ctx_files = json.loads(row["context_files_json"])
    prompt_text = (
        f"Execute Ticket {row['id']}: {row['title']}\n\n"
        f"STRICT CONTEXT BOUNDARY (Only read/modify these files unless strictly required):\n"
        + "\n".join(f"- {f}" for f in ctx_files)
        + f"\n\nSCOPE & REQUIREMENTS:\n{row['scope_boundaries']}\n\n"
        f"ENGINEERING RULES:\n"
        f"1. Zero external dependencies (Python 3 stdlib + vanilla ES6/CSS only).\n"
        f"2. Write/update feature recipe at `{row['recipe_file']}`.\n"
        f"3. Create >=20 deterministic unit tests in `{row['test_module']}`.\n"
        f"4. Verify with: `python dev_tools/orchestrate_v2_overhaul.py verify {row['id']}`.\n"
    )

    payload = {
        "TypeName": "self",
        "Model": row["model_tier"],
        "Role": row["role"],
        "TicketId": row["id"],
        "Wave": row["wave"],
        "ContextFiles": ctx_files,
        "TestModule": row["test_module"],
        "Prompt": prompt_text,
    }

    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print("=" * 88)
        print(f"SUBAGENT DISPATCH PAYLOAD FOR {row['id']} (Model: {row['model_tier']} | Wave {row['wave']})")
        print("=" * 88)
        print(f"Role       : {row['role']}")
        print(f"Model      : {row['model_tier']}")
        print(f"Test Suite : {row['test_module']}")
        print("-" * 88)
        print(prompt_text)
        print("=" * 88)


def verify_ticket(ticket_id: str) -> None:
    ensure_orchestration_schema()
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT test_module, context_files_json FROM ticket_execution_meta WHERE ticket_id = ?",
            (ticket_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        print(f"[ERROR] Ticket '{ticket_id}' not found.")
        sys.exit(1)

    test_mod = row["test_module"]
    ctx_files = json.loads(row["context_files_json"])
    test_path = REPO_ROOT / test_mod

    cmd = [sys.executable, "-m", "unittest"]
    if test_path.exists():
        cmd.append(test_mod)
    else:
        print(f"[WARN] Dedicated test module `{test_mod}` does not exist yet; running selective tests for context files...")
        from dev_tools.selective_test_runner import find_tests_for_files
        related = find_tests_for_files(ctx_files)
        for rel in sorted(related):
            cmd.append(f"tests/{rel}")

    print(f"[VERIFY {ticket_id}] Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if res.returncode == 0:
        conn = get_db_connection()
        try:
            conn.execute("UPDATE tickets SET status = 'Done' WHERE id = ?", (ticket_id,))
            conn.commit()
        finally:
            conn.close()
    sys.exit(res.returncode)


def mark_all_done() -> None:
    ensure_orchestration_schema()
    conn = get_db_connection()
    try:
        conn.execute("UPDATE tickets SET status = 'Done' WHERE id LIKE 'AIUM-10%'")
        conn.execute("UPDATE epics SET status = 'Done' WHERE id = 'EPIC-V2.5-UNIFIED-OVERHAUL'")
        conn.commit()
        print("[OK] Marked EPIC-V2.5-UNIFIED-OVERHAUL and AIUM-1001..1012 as Done.")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Usage Monitor v2.5 Multi-Model Orchestrator")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init-plan", help="Seed EPIC-V2.5-UNIFIED-OVERHAUL and 12 model-routed tickets into dev_roadmap.db")
    sub.add_parser("mark-done", help="Mark EPIC-V2.5-UNIFIED-OVERHAUL and all v2.5 tickets as Done")

    p_plan = sub.add_parser("plan", help="Display multi-wave model-routed execution plan")
    p_plan.add_argument("--wave", type=int, default=None, help="Filter by wave number (1-5)")
    p_plan.add_argument("--model", type=str, choices=["flash_lite", "flash", "pro"], default=None, help="Filter by model tier")

    p_prompt = sub.add_parser("prompt", help="Generate bounded subagent dispatch prompt for a ticket")
    p_prompt.add_argument("ticket_id", type=str, help="Ticket ID (e.g. AIUM-1001)")
    p_prompt.add_argument("--json", action="store_true", help="Output as JSON for programmatic dispatch")

    p_verify = sub.add_parser("verify", help="Run targeted unit tests for a ticket")
    p_verify.add_argument("ticket_id", type=str, help="Ticket ID (e.g. AIUM-1001)")

    args = parser.parse_args()
    if args.command == "init-plan":
        init_plan()
    elif args.command == "mark-done":
        mark_all_done()
    elif args.command == "plan":
        print_plan(wave_filter=args.wave, model_filter=args.model)
    elif args.command == "prompt":
        generate_subagent_prompt(args.ticket_id, as_json=args.json)
    elif args.command == "verify":
        verify_ticket(args.ticket_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import sqlite3
import argparse
import json
import datetime
import time
import unittest

from dev_tools.selective_test_runner import (
    get_git_changed_files,
    find_tests_for_files,
    build_selective_suite
)

DB_PATH = str(REPO_ROOT / "dev_roadmap.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS epics (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id TEXT PRIMARY KEY,
            epic_id TEXT,
            title TEXT NOT NULL,
            description TEXT,
            ticket_type TEXT NOT NULL,
            status TEXT NOT NULL,
            priority TEXT NOT NULL,
            recipe_file TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(epic_id) REFERENCES epics(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS test_runs (
            id TEXT PRIMARY KEY,
            cycle_identifier TEXT NOT NULL,
            run_date TEXT NOT NULL,
            ticket_id TEXT,
            passed INTEGER,
            failed INTEGER,
            errors INTEGER,
            duration REAL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS test_results (
            run_id TEXT NOT NULL,
            test_name TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            duration REAL,
            PRIMARY KEY (run_id, test_name),
            FOREIGN KEY(run_id) REFERENCES test_runs(id)
        )
    ''')

    # Seed initial Epic and Tickets
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    cursor.execute("SELECT COUNT(*) FROM epics WHERE id = 'EPIC-AIUM-POC'")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO epics (id, title, description, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            'EPIC-AIUM-POC',
            'AI Usage Monitor Core Platform & Claude POC',
            'Zero-dependency cross-provider AI usage tracker with native Windows DPAPI, Tray icon, Web UI, and Claude multi-mode ingestion.',
            'In Progress',
            now, now
        ))

    tickets_seed = [
        ('AIUM-101', 'EPIC-AIUM-POC', 'Windows Native DPAPI Security Vault', 'Zero-dependency native encryption using crypt32.dll for secure credential storage.', 'Feature', 'Todo', 'Critical', 'feature_recipes/FR-101-DPAPI-SECURITY-VAULT.md'),
        ('AIUM-102', 'EPIC-AIUM-POC', 'Proactive Redacted Diagnostics & Logging Engine', 'Structured error tracker with automated token/key sanitization and 1-click diagnostic export.', 'Feature', 'Todo', 'High', 'feature_recipes/FR-104-PROACTIVE-DIAGNOSTICS.md'),
        ('AIUM-103', 'EPIC-AIUM-POC', 'Core SQLite Usage Time-Series Storage', 'Local database tracking provider tokens, sessions, costs, rate limits, and hourly/daily trends.', 'Feature', 'Todo', 'Critical', 'feature_recipes/FR-102-CLAUDE-USAGE-PROVIDER.md'),
        ('AIUM-104', 'EPIC-AIUM-POC', 'Claude Multi-Mode Usage Provider', 'Anthropic API poller, Transparent Local Proxy, CLI log scanner, and mock fallback.', 'Feature', 'Todo', 'Critical', 'feature_recipes/FR-102-CLAUDE-USAGE-PROVIDER.md'),
        ('AIUM-105', 'EPIC-AIUM-POC', 'Multi-Provider Framework (Gemini, Ollama, M365 Copilot)', 'Pluggable provider architecture with initial interfaces and coming soon indicators.', 'Feature', 'Todo', 'Medium', 'feature_recipes/FR-102-CLAUDE-USAGE-PROVIDER.md'),
        ('AIUM-106', 'EPIC-AIUM-POC', 'Zero-Dependency HTTP Server & REST API', 'ThreadingHTTPServer serving REST API and canonical SPA web components.', 'Feature', 'Todo', 'High', 'feature_recipes/FR-103-WINDOWS-TRAY-AND-WIDGET.md'),
        ('AIUM-107', 'EPIC-AIUM-POC', 'Web UI Dashboard & Canonical Components', 'Stunning dark-mode glassmorphic dashboard with live token gauges and session timeline.', 'Feature', 'Todo', 'High', 'feature_recipes/FR-103-WINDOWS-TRAY-AND-WIDGET.md'),
        ('AIUM-108', 'EPIC-AIUM-POC', 'Windows System Tray & Mini Status Bar Widget', 'Shell_NotifyIconW native tray icon and compact status bar widget view.', 'Feature', 'Todo', 'High', 'feature_recipes/FR-103-WINDOWS-TRAY-AND-WIDGET.md'),
        ('AIUM-109', 'EPIC-AIUM-POC', 'End-to-End TDD Verification & Release v0.1.0', 'Comprehensive unit tests (>=20), 100% error-free pass rate, and release compilation.', 'Task', 'Todo', 'Critical', 'feature_recipes/FR-101-DPAPI-SECURITY-VAULT.md')
    ]

    for t_id, ep_id, title, desc, t_type, status, priority, recipe in tickets_seed:
        cursor.execute("SELECT COUNT(*) FROM tickets WHERE id = ?", (t_id,))
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO tickets (id, epic_id, title, description, ticket_type, status, priority, recipe_file, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (t_id, ep_id, title, desc, t_type, status, priority, recipe, now, now))

    conn.commit()
    conn.close()
    print("[OK] Database initialized successfully with Epics and Tickets.")

def list_status():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM epics")
    epics = cursor.fetchall()
    print("\n" + "=" * 70)
    print("AI USAGE MONITOR - ROADMAP STATUS")
    print("=" * 70)
    for epic in epics:
        print(f"\n[EPIC] {epic['id']} : {epic['title']} [{epic['status']}]")
        print(f"       {epic['description']}")
        cursor.execute("SELECT * FROM tickets WHERE epic_id = ?", (epic['id'],))
        tickets = cursor.fetchall()
        print("-" * 70)
        for t in tickets:
            print(f"  * {t['id']:<10} [{t['status']:<11}] ({t['priority']:<8}) {t['title']}")
            if t['recipe_file']:
                print(f"      Recipe: {t['recipe_file']}")
    print("=" * 70 + "\n")
    conn.close()

def update_ticket(ticket_id: str, status: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cursor.execute("UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?", (status, now, ticket_id))
    conn.commit()
    conn.close()
    print(f"[OK] Ticket {ticket_id} status updated to '{status}'")

def run_tests(ticket_id: str = None, cycle: str = "Dev Cycle"):
    conn = get_db_connection()
    cursor = conn.cursor()

    tests_dir = REPO_ROOT / "tests"
    if not tests_dir.exists():
        tests_dir.mkdir(parents=True, exist_ok=True)

    loader = unittest.TestLoader()
    suite = loader.discover(str(tests_dir), pattern="test_*.py")

    start_time = time.time()
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    duration = time.time() - start_time

    run_id = f"RUN-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_date = datetime.datetime.now(datetime.timezone.utc).isoformat()
    passed = result.testsRun - len(result.failures) - len(result.errors)

    cursor.execute('''
        INSERT INTO test_runs (id, cycle_identifier, run_date, ticket_id, passed, failed, errors, duration)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (run_id, cycle, run_date, ticket_id, passed, len(result.failures), len(result.errors), duration))

    for test, err in result.failures:
        cursor.execute('''
            INSERT INTO test_results (run_id, test_name, status, error_message, duration)
            VALUES (?, ?, ?, ?, ?)
        ''', (run_id, str(test), 'FAIL', err, 0.0))

    for test, err in result.errors:
        cursor.execute('''
            INSERT INTO test_results (run_id, test_name, status, error_message, duration)
            VALUES (?, ?, ?, ?, ?)
        ''', (run_id, str(test), 'ERROR', err, 0.0))

    conn.commit()
    conn.close()

    print(f"\n[TEST SUMMARY] Total: {result.testsRun} | Passed: {passed} | Failures: {len(result.failures)} | Errors: {len(result.errors)} | Time: {duration:.2f}s")
    if not result.wasSuccessful():
        sys.exit(1)

def generate_release_notes(version: str, out_file: str = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tickets WHERE status = 'Done'")
    done_tickets = cursor.fetchall()

    notes = [
        f"# Release Notes - Version {version}",
        f"**Date**: {datetime.datetime.now().strftime('%Y-%m-%d')}",
        "",
        "## Summary",
        "Initial release of AI Usage Monitor featuring zero-dependency Python backend, Windows DPAPI encryption, native Windows Tray, modern web dashboard, and Claude multi-mode usage tracking.",
        "",
        "## Completed Features & Tickets",
        ""
    ]

    for t in done_tickets:
        notes.append(f"- **[{t['id']}] {t['title']}** ({t['ticket_type']}): {t['description']}")

    notes_text = "\n".join(notes)
    target = Path(out_file) if out_file else REPO_ROOT / f"release_notes/RELEASE_{version}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(notes_text, encoding="utf-8")
    print(f"[OK] Release notes generated at {target}")
    conn.close()

def main():
    parser = argparse.ArgumentParser(description="AI Usage Monitor Developer Roadmap & WoW Tool")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Initialize developer SQLite database and ingest initial tickets")
    subparsers.add_parser("status", help="Print roadmap status")

    test_parser = subparsers.add_parser("run-tests", help="Run test suite and record results")
    test_parser.add_argument("--ticket", type=str, help="Linked Ticket ID")
    test_parser.add_argument("--cycle", type=str, default="Dev Cycle", help="Cycle name")

    update_parser = subparsers.add_parser("update-ticket", help="Update ticket status")
    update_parser.add_argument("id", type=str, help="Ticket ID")
    update_parser.add_argument("--status", type=str, required=True, choices=["Todo", "In Progress", "In Review", "Done"])

    notes_parser = subparsers.add_parser("generate-release-notes", help="Generate release notes")
    notes_parser.add_argument("--version", type=str, required=True, help="Release version (e.g. v0.1.0)")
    notes_parser.add_argument("--out", type=str, help="Output file path")

    args = parser.parse_args()

    if args.command == "init":
        init_db()
    elif args.command == "status":
        list_status()
    elif args.command == "update-ticket":
        update_ticket(args.id, args.status)
    elif args.command == "run-tests":
        run_tests(ticket_id=args.ticket, cycle=args.cycle)
    elif args.command == "generate-release-notes":
        generate_release_notes(args.version, args.out)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

import os
import sys
import re
import sqlite3
import subprocess
import unittest
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

DEFAULT_DB_PATH = "dev_roadmap.db"

def parse_git_status_output(raw_status: str) -> List[str]:
    """Parses raw git status --porcelain output and returns modified/untracked file paths."""
    files: List[str] = []
    for line in raw_status.strip().splitlines():
        if not line:
            continue
        status_code = line[:2]
        filepath = line[2:].strip()
        if filepath.startswith('"') and filepath.endswith('"'):
            filepath = filepath[1:-1]
        filepath = filepath.replace("\\", "/")
        if "D" in status_code:
            continue
        if "->" in filepath:
            filepath = filepath.split("->")[-1].strip()
        if filepath and filepath not in files:
            files.append(filepath)
    return files

def get_git_changed_files(repo_root: Optional[str] = None) -> List[str]:
    """Captures all untracked, staged, and unstaged changed files via git."""
    root = repo_root or str(Path(__file__).resolve().parent.parent)
    changed: List[str] = []

    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False
        )
        if res.returncode == 0:
            changed.extend(parse_git_status_output(res.stdout))
    except Exception:
        pass

    return list(dict.fromkeys(changed))

def find_tests_for_files(changed_files: List[str], repo_root: Optional[str] = None) -> List[str]:
    """Maps modified files to their relevant test file paths."""
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent
    tests_dir = root / "tests"
    if not tests_dir.exists():
        return []

    all_test_files = [f.name for f in tests_dir.glob("test_*.py")]
    matched_tests: Set[str] = set()

    for cf in changed_files:
        p = Path(cf)
        if p.name.startswith("test_") and p.name.endswith(".py"):
            matched_tests.add(p.name)
            continue

        base_stem = p.stem.lower()
        for tf in all_test_files:
            if base_stem in tf.lower():
                matched_tests.add(tf)

    if not matched_tests:
        return all_test_files

    return sorted(list(matched_tests))

def build_selective_suite(test_files: List[str], repo_root: Optional[str] = None) -> unittest.TestSuite:
    """Builds a unittest.TestSuite containing only the specified test files."""
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent
    tests_dir = root / "tests"
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for tf in test_files:
        test_path = tests_dir / tf
        if test_path.exists():
            mod_name = f"tests.{test_path.stem}"
            try:
                mod_suite = loader.loadTestsFromName(mod_name)
                suite.addTests(mod_suite)
            except Exception as e:
                print(f"[WARN] Failed to load {mod_name}: {e}")

    return suite

import os
import sys
import re
import json
import time
import datetime
import platform
import threading
from pathlib import Path
from enum import Enum
from typing import Dict, Any, List, Optional

from backend.config import LOGS_DIR

class ErrorCategory(str, Enum):
    AUTH_FAILURE = "AUTH_FAILURE"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    PROXY_BLOCKED = "PROXY_BLOCKED"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    SYSTEM_ERROR = "SYSTEM_ERROR"

# Regex patterns for sensitive credentials
PATTERNS = [
    # Anthropic API & Session Keys
    (re.compile(r"sk-ant-(api\d{2}|sid\d{2})-[A-Za-z0-9_\-]+", re.IGNORECASE), r"sk-ant-***"),
    # Generic / OpenAI API Keys
    (re.compile(r"sk-(proj-)?[A-Za-z0-9_\-]{16,}", re.IGNORECASE), r"sk-***"),
    # Google API Keys
    (re.compile(r"AIza[0-9A-Za-z_\-]{30,}", re.IGNORECASE), r"AIza***"),
    # Bearer tokens
    (re.compile(r"Bearer\s+[A-Za-z0-9\-_.~+/]+=*", re.IGNORECASE), r"Bearer ***"),
    # Windows User directory path
    (re.compile(r"([A-Za-z]:\\Users\\)([^\\]+)(\\)", re.IGNORECASE), r"\1<REDACTED_USER>\3"),
    # Unix user home path
    (re.compile(r"(/home/)([^/]+)(/)", re.IGNORECASE), r"\1<REDACTED_USER>\3"),
]

def redact_sensitive_text(text: str) -> str:
    """Replaces credentials, keys, and private paths with masked strings."""
    if not text or not isinstance(text, str):
        return str(text)

    redacted = text
    for pattern, repl in PATTERNS:
        redacted = pattern.sub(repl, redacted)
    return redacted

class DiagnosticsEngine:
    """
    Proactive Diagnostics and Troubleshooting Engine.
    Records sanitized errors, health metrics, and exports clean bug-reporting bundles.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DiagnosticsEngine, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, log_dir: Optional[str] = None, max_history: int = 150):
        if self._initialized:
            return

        self.log_dir = Path(log_dir or LOGS_DIR)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "diagnostics.log"
        self.max_history = max_history
        self._history: List[Dict[str, Any]] = []
        self._provider_health: Dict[str, Dict[str, Any]] = {
            "claude": {"status": "HEALTHY", "error_count": 0, "last_error": None, "last_sync": None},
            "gemini": {"status": "NOT_CONFIGURED", "error_count": 0, "last_error": None, "last_sync": None},
            "copilot": {"status": "STANDBY", "error_count": 0, "last_error": None, "last_sync": None},
            "ollama": {"status": "OFFLINE", "error_count": 0, "last_error": None, "last_sync": None},
        }
        self._boot_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._history_lock = threading.Lock()
        self._initialized = True

    def record_error(
        self,
        category: ErrorCategory,
        provider: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        exception: Optional[Exception] = None
    ) -> Dict[str, Any]:
        """Records a sanitized error event."""
        sanitized_msg = redact_sensitive_text(str(message))
        sanitized_details = {}
        if details:
            for k, v in details.items():
                sanitized_details[k] = redact_sensitive_text(str(v)) if isinstance(v, str) else v

        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        event = {
            "id": f"ERR-{int(time.time()*1000)}",
            "timestamp": now_utc,
            "category": category.value if isinstance(category, ErrorCategory) else str(category),
            "provider": provider.lower(),
            "message": sanitized_msg,
            "details": sanitized_details,
            "exception_type": exception.__class__.__name__ if exception else None
        }

        with self._history_lock:
            self._history.insert(0, event)
            if len(self._history) > self.max_history:
                self._history.pop()

            # Update provider health
            prov = provider.lower()
            if prov not in self._provider_health:
                self._provider_health[prov] = {"status": "DEGRADED", "error_count": 0, "last_error": None, "last_sync": None}

            self._provider_health[prov]["error_count"] += 1
            self._provider_health[prov]["last_error"] = sanitized_msg
            self._provider_health[prov]["status"] = "ERROR" if self._provider_health[prov]["error_count"] >= 3 else "DEGRADED"

        # Write to log file
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except Exception:
            pass

        return event

    def mark_provider_healthy(self, provider: str):
        """Resets error counter for a provider on successful interaction."""
        prov = provider.lower()
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._history_lock:
            if prov in self._provider_health:
                self._provider_health[prov]["status"] = "HEALTHY"
                self._provider_health[prov]["error_count"] = 0
                self._provider_health[prov]["last_sync"] = now_utc
            else:
                self._provider_health[prov] = {
                    "status": "HEALTHY",
                    "error_count": 0,
                    "last_error": None,
                    "last_sync": now_utc
                }

    def get_recent_errors(self, limit: int = 50, provider: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns recent error events."""
        with self._history_lock:
            if provider:
                filtered = [e for e in self._history if e["provider"] == provider.lower()]
                return filtered[:limit]
            return self._history[:limit]

    def clear_errors(self):
        """Clears in-memory error history."""
        with self._history_lock:
            self._history.clear()
            for p in self._provider_health.values():
                p["error_count"] = 0
                p["status"] = "HEALTHY"

    def export_diagnostic_bundle(self) -> Dict[str, Any]:
        """Generates a comprehensive sanitized diagnostic export bundle."""
        with self._history_lock:
            errors_copy = list(self._history[:50])
            health_copy = dict(self._provider_health)

        return {
            "app_version": "0.1.0",
            "boot_time": self._boot_time,
            "export_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "system_info": {
                "os": platform.system(),
                "os_release": platform.release(),
                "python_version": platform.python_version(),
                "architecture": platform.architecture()[0]
            },
            "provider_health": health_copy,
            "recent_errors": errors_copy,
            "error_summary": {
                "total_recorded": len(self._history),
                "unresolved_errors": sum(p["error_count"] for p in health_copy.values())
            }
        }

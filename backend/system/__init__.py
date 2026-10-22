"""
AI Usage Monitor - System & OS Lifecycle Integration Package
Provides zero-dependency Windows auto-start registration, single-instance PID locks,
and background daemon supervision while preserving user-scoped Windows DPAPI access.
"""

from backend.system.windows_service import (
    WindowsServiceManager,
    RotatingFileStream,
    setup_daemon_logging,
)

__all__ = [
    "WindowsServiceManager",
    "RotatingFileStream",
    "setup_daemon_logging",
]

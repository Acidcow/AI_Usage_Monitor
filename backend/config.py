import os
import sys
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
FRONTEND_DIR = BASE_DIR / "frontend"

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Database Paths
DB_PATH = str(DATA_DIR / "usage_stats.db")
CREDENTIALS_FILE = str(DATA_DIR / "vault_credentials.enc")

# Server Config
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
PROXY_PORT = 8766

# Poll Intervals (seconds)
DEFAULT_POLL_INTERVAL = 30
TRAY_REFRESH_INTERVAL = 5

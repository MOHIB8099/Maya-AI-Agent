"""
Maya AI - Advanced Reminders + Scheduler
Single-file reminder engine.

Features:
- One-time and relative reminders
- Exact date/time
- Daily/weekly/monthly/weekday/interval recurrence
- Snooze, cancel, pause/resume, edit
- Upcoming/overdue/history
- SQLite persistence
- Restart/missed-reminder recovery
- Duplicate prevention
- Timezone-aware scheduling
- Optional Windows notification (winotify)
- Optional Maya voice announcement
- Background scheduler
- Central execute_reminder_action() router

Optional:
    pip install winotify
"""

from __future__ import annotations

import calendar
import ctypes
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "maya_reminders.db"

DEFAULT_USER_ID = "default"
DEFAULT_TIMEZONE = os.getenv("MAYA_TIMEZONE", "Asia/Kolkata")
POLL_INTERVAL_SECONDS = 1.0
MISSED_GRACE_SECONDS = 12 * 60 * 60
DUPLICATE_WINDOW_SECONDS = 90

VALID_STATUS = {"active", "paused", "completed", "cancelled", "missed"}
VALID_RECURRENCE = {"none", "interval", "daily", "weekly", "monthly", "weekdays"}

WEEKDAY_NAME_TO_INT = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

_db_lock = threading.RLock()
_scheduler_lock = threading.RLock()
_scheduler_stop = threading.Event()
_scheduler_thread: threading.Thread | None = None
_scheduler_started = False

try:
    from winotify import Notification
except Exception:
    Notification = None


# =========================================================
# DATABASE + HELPERS
# =========================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat(timespec="seconds")


def get_timezone(name: str | None = None) -> ZoneInfo:
    try:
        return ZoneInfo((name or DEFAULT_TIMEZONE).strip())
    except Exception:
        return ZoneInfo("UTC")


def parse_datetime(value: str | datetime, timezone_name: str | None = None) -> datetime:
    tz = get_timezone(timezone_name)

    if isinstance(value, datetime):
        dt = value
    else:

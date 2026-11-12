"""The one helper that writes service timestamps (CLAUDE.md section 6, Timestamps)."""
from datetime import datetime, timezone


def utc_now_iso():
    """Current time as UTC ISO 8601 with an explicit offset, e.g. 2026-11-11T21:04:05+00:00."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

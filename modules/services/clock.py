"""The only module that reads the system clock (CLAUDE.md section 6, Timestamps; decision H2).

Services never call the clock. A ServiceContext carries `now` (UTC ISO 8601) and `today` (the
company's local date); contexts are built by the context builders, which call utc_now_iso() here.
"""
import logging
from datetime import datetime, timezone

_logger = logging.getLogger("strataledger.clock")


def utc_now_iso():
    """Current time as UTC ISO 8601 with an explicit offset, e.g. 2026-11-11T21:04:05+00:00."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def local_today(now_iso, tz_name):
    """The company-local ISO date for a UTC instant.

    An entry made at 6 pm in California must not default to tomorrow's date, so `today` follows
    company_settings.timezone, not UTC. If the zone is unknown, or the tzdata package is not
    installed, the UTC date is used and a warning is logged.
    """
    instant = datetime.fromisoformat(now_iso)
    if not tz_name or tz_name == "UTC":
        return instant.astimezone(timezone.utc).date().isoformat()
    try:
        from zoneinfo import ZoneInfo
        return instant.astimezone(ZoneInfo(tz_name)).date().isoformat()
    except Exception as error:  # noqa: BLE001  (ZoneInfoNotFoundError, ValueError, missing tzdata)
        _logger.warning("time zone %r is not available (%s); using the UTC date", tz_name, error)
        return instant.astimezone(timezone.utc).date().isoformat()

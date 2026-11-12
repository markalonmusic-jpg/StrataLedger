"""The only module that reads the system clock (CLAUDE.md section 6, Timestamps; decision H2).

Services never call the clock. A ServiceContext carries `now` (UTC ISO 8601) and `today` (the
company's local date); contexts are built by the context builders, which call utc_now_iso() here.
"""
import logging
from datetime import datetime, timezone

from modules.services.errors import InstallationError

_logger = logging.getLogger("strataledger.clock")


def utc_now_iso():
    """Current time as UTC ISO 8601 with an explicit offset, e.g. 2026-11-11T21:04:05+00:00."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def local_today(now_iso, tz_name):
    """The company-local ISO date for a UTC instant.

    An entry made at 6 pm in California must not default to tomorrow's date, so `today` follows
    company_settings.timezone, not UTC. A company with no time zone set (built before 2.4a) uses UTC.
    If the zone cannot be loaded (the tzdata package is missing or damaged) this raises
    InstallationError: there is no silent fallback to the UTC date.
    """
    instant = datetime.fromisoformat(now_iso)
    if not tz_name or tz_name == "UTC":
        return instant.astimezone(timezone.utc).date().isoformat()
    try:
        from zoneinfo import ZoneInfo
        zone = ZoneInfo(tz_name)
    except Exception as error:  # noqa: BLE001  (ZoneInfoNotFoundError, ValueError, missing tzdata)
        _logger.error("time zone %r could not be loaded: %s", tz_name, error)
        raise InstallationError(
            f"Time zone data is missing for {tz_name}; reinstall StrataLedger.") from None
    return instant.astimezone(zone).date().isoformat()

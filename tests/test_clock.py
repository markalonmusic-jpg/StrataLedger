"""clock.py: the one place that reads the system clock, and the company-local date (decision H2)."""
import logging

import pytest

from modules.services import clock


def _has_tzdata():
    try:
        import zoneinfo
        zoneinfo.ZoneInfo("America/Los_Angeles")
        return True
    except Exception:  # noqa: BLE001
        return False


needs_tzdata = pytest.mark.skipif(not _has_tzdata(), reason="the tzdata package is not installed")


def test_utc_now_iso_shape():
    stamp = clock.utc_now_iso()
    assert stamp.endswith("+00:00") and len(stamp) == 25


def test_utc_needs_no_tzdata():
    assert clock.local_today("2026-11-11T23:30:00+00:00", "UTC") == "2026-11-11"


@needs_tzdata
def test_california_evening_is_still_today():
    # 6 pm on 11 Nov in California is 02:00 UTC on 12 Nov.
    assert clock.local_today("2026-11-12T02:00:00+00:00", "America/Los_Angeles") == "2026-11-11"


@needs_tzdata
def test_manila_morning_is_already_tomorrow():
    assert clock.local_today("2026-11-11T20:00:00+00:00", "Asia/Manila") == "2026-11-12"


@needs_tzdata
def test_daylight_saving_boundary():
    assert clock.local_today("2026-03-08T09:30:00+00:00", "America/Los_Angeles") == "2026-03-08"
    assert clock.local_today("2026-03-08T07:30:00+00:00", "America/Los_Angeles") == "2026-03-07"


def test_unknown_or_missing_zone_falls_back_to_the_utc_date_and_logs(caplog):
    with caplog.at_level(logging.WARNING):
        assert clock.local_today("2026-11-11T23:30:00+00:00", "Mars/Olympus") == "2026-11-11"
    assert "Mars/Olympus" in caplog.text
    assert clock.local_today("2026-11-11T23:30:00+00:00", None) == "2026-11-11"

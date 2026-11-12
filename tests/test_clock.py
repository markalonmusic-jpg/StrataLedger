"""clock.py: the one place that reads the system clock, and the company-local date (decision H2).

tzdata is a hard requirement (requirements.txt): these tests never skip.
"""
import zoneinfo

import pytest

from modules.services import clock
from modules.services.errors import InstallationError


def test_tzdata_is_installed():
    import tzdata  # noqa: F401  (the test environment must have it, like the installed app)
    zoneinfo.ZoneInfo("America/Los_Angeles")
    zoneinfo.ZoneInfo("Asia/Manila")


def test_utc_now_iso_shape():
    stamp = clock.utc_now_iso()
    assert stamp.endswith("+00:00") and len(stamp) == 25


def test_utc_and_no_zone_use_the_utc_date():
    assert clock.local_today("2026-11-11T23:30:00+00:00", "UTC") == "2026-11-11"
    assert clock.local_today("2026-11-11T23:30:00+00:00", None) == "2026-11-11"


def test_california_evening_is_still_today():
    # 6 pm on 11 Nov in California is 02:00 UTC on 12 Nov.
    assert clock.local_today("2026-11-12T02:00:00+00:00", "America/Los_Angeles") == "2026-11-11"


def test_manila_morning_is_already_tomorrow():
    assert clock.local_today("2026-11-11T20:00:00+00:00", "Asia/Manila") == "2026-11-12"


def test_daylight_saving_boundary():
    assert clock.local_today("2026-03-08T09:30:00+00:00", "America/Los_Angeles") == "2026-03-08"
    assert clock.local_today("2026-03-08T07:30:00+00:00", "America/Los_Angeles") == "2026-03-07"


def test_an_unloadable_zone_is_an_installation_error_not_a_silent_fallback(monkeypatch):
    def missing(name):
        raise zoneinfo.ZoneInfoNotFoundError(f"No time zone found with key {name}")
    monkeypatch.setattr(zoneinfo, "ZoneInfo", missing)
    with pytest.raises(InstallationError) as caught:
        clock.local_today("2026-11-11T23:30:00+00:00", "America/Los_Angeles")
    assert "reinstall" in str(caught.value).lower() and "America/Los_Angeles" in str(caught.value)


def test_unknown_zone_name_is_also_an_error():
    with pytest.raises(InstallationError):
        clock.local_today("2026-11-11T23:30:00+00:00", "Mars/Olympus")

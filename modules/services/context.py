"""Who is acting: passed as the first argument to every service function.

The context carries identity and where the databases are, never the user's role:
authorize() reads the role fresh from the master database on every call, so a
role change applies on the user's next action.
"""
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from modules.services import clock
from modules.services.errors import ValidationError

ORIGINS = ("Human", "Agent", "Import", "System")


@dataclass(frozen=True)
class ServiceContext:
    user_id: int
    company_id: int
    origin: str
    company_db_path: str
    master_db_path: str
    agent_run_id: Optional[int] = None
    now: Optional[str] = None      # UTC ISO 8601 with offset; filled here (a context builder) when omitted
    today: Optional[str] = None    # the company-local ISO date; the UTC date until open_company sets it
    read_only: bool = False        # the company file is open read-only (Auditor, design 6); no company writes

    def __post_init__(self):
        if self.origin not in ORIGINS:
            raise ValidationError(f"origin must be one of {', '.join(ORIGINS)}; got {self.origin!r}")
        object.__setattr__(self, "company_db_path", os.fspath(self.company_db_path))
        object.__setattr__(self, "master_db_path", os.fspath(self.master_db_path))
        now = self.now if self.now is not None else clock.utc_now_iso()
        if not isinstance(now, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(\+00:00|Z)", now):
            raise ValidationError(f"now must be a UTC ISO 8601 time like 2026-01-01T00:00:00+00:00; got {now!r}")
        today = self.today if self.today is not None else now[:10]
        try:
            if not isinstance(today, str) or not re.fullmatch(r"\d{4}-\d\d-\d\d", today):
                raise ValueError(today)
            date.fromisoformat(today)
            datetime.fromisoformat(now.replace("Z", "+00:00"))
        except ValueError:
            raise ValidationError(f"today must be an ISO date like 2026-01-01; got {today!r}") from None
        object.__setattr__(self, "now", now)
        object.__setattr__(self, "today", today)

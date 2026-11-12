"""Who is acting: passed as the first argument to every service function.

The context carries identity and where the databases are, never the user's role:
authorize() reads the role fresh from the master database on every call, so a
role change applies on the user's next action.
"""
import os
from dataclasses import dataclass
from typing import Optional

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

    def __post_init__(self):
        if self.origin not in ORIGINS:
            raise ValidationError(f"origin must be one of {', '.join(ORIGINS)}; got {self.origin!r}")
        object.__setattr__(self, "company_db_path", os.fspath(self.company_db_path))
        object.__setattr__(self, "master_db_path", os.fspath(self.master_db_path))

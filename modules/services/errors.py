"""Typed service-layer exceptions.

Services raise these; the UI catches them and shows a dialog (CLAUDE.md rules 5
and 12). SchemaUpgradeBlockedError stays in modules/database.py.
"""


class ServiceError(Exception):
    """Base class for every error a service function raises on purpose."""


class ValidationError(ServiceError):
    """Input is missing, malformed or breaks a business rule."""


class NotFoundError(ServiceError):
    """A referenced record does not exist."""


class PostingError(ServiceError):
    """A ledger posting was refused (unbalanced, not postable, already posted...)."""


class KeyUnavailableError(PostingError):
    """The ledger chain key cannot be had on this computer, so nothing can be posted (decision K3).

    The message names at most a key id, never key material.
    """


class KeyStoreLockedError(KeyUnavailableError):
    """The installation key is locked on this computer (DPAPI failed and the Master has not restored it with the
    recovery code yet), so no new ledger key can be made: creating a company is refused (KS6)."""


class PermissionDeniedError(ServiceError):
    """The acting user lacks the permission for this action."""


class PeriodClosedError(ServiceError):
    """The fiscal period is closed to this kind of entry."""


class AuthenticationError(ServiceError):
    """Login or password verification failed. The message never says which part was wrong."""


class LoginThrottledError(ServiceError):
    """Too many failed attempts for this username; retry_after is the wait in whole seconds."""

    def __init__(self, retry_after):
        self.retry_after = int(retry_after)
        super().__init__(f"Too many failed attempts; try again in {self.retry_after} seconds")


class PasswordChangeRequiredError(ServiceError):
    """The user's password was reset; only change_password is allowed until it is changed."""


class DuplicateContactError(ValidationError):
    """A contact with the same name, tax ID or email exists; the caller must confirm to create anyway.

    `matches` is the list find_duplicates returned (tax IDs already masked for the acting user).
    """

    def __init__(self, message, matches):
        super().__init__(message)
        self.matches = matches


class InstallationError(ServiceError):
    """Something the installation must provide is missing or damaged (for example time zone data)."""

import pytest

from modules.database import SchemaUpgradeBlockedError
from modules.services import errors


@pytest.mark.parametrize(
    "name",
    ["ValidationError", "NotFoundError", "PostingError", "PermissionDeniedError", "PeriodClosedError"],
)
def test_typed_errors_derive_from_service_error(name):
    cls = getattr(errors, name)
    assert issubclass(cls, errors.ServiceError)
    assert issubclass(errors.ServiceError, Exception)
    assert str(cls("message")) == "message"


def test_schema_upgrade_blocked_error_stays_in_database():
    assert not hasattr(errors, "SchemaUpgradeBlockedError")
    assert issubclass(SchemaUpgradeBlockedError, Exception)

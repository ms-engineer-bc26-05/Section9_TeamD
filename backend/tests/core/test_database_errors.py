"""DB障害の分類テスト。実DBには接続しない。"""

from socket import gaierror

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from app.core.database_errors import is_database_connection_error


@pytest.mark.parametrize(
    "error",
    [
        ConnectionRefusedError("dummy"),
        ConnectionResetError("dummy"),
        gaierror("dummy"),
        OperationalError(
            "SELECT dummy",
            {},
            ConnectionRefusedError("dummy"),
        ),
    ],
)
def test_connection_failures_are_recognized(error):
    assert is_database_connection_error(error) is True


@pytest.mark.parametrize(
    "error",
    [
        IntegrityError("INSERT dummy", {}, Exception("dummy")),
        ProgrammingError("SELECT dummy", {}, Exception("dummy")),
        OperationalError("SELECT dummy", {}, Exception("dummy")),
        RuntimeError("connection refused"),
        TimeoutError("dummy"),
    ],
)
def test_other_errors_are_not_classified_as_connection_failures(error):
    assert is_database_connection_error(error) is False


@pytest.mark.parametrize("attribute", ["sqlstate", "pgcode"])
@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("08000", True),
        ("08001", True),
        ("08003", True),
        ("08004", True),
        ("08006", True),
        ("57P01", True),
        ("57P02", True),
        ("57P03", True),
        ("23505", False),
        ("42601", False),
        ("57014", False),
        (None, False),
        (123, False),
    ],
)
def test_sqlstate_classification(attribute, wrapped, code, expected):
    original = Exception("dummy")
    setattr(original, attribute, code)

    error = (
        OperationalError("SELECT dummy", {}, original)
        if wrapped
        else original
    )

    assert is_database_connection_error(error) is expected

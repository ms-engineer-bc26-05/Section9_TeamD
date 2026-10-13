"""メモのDB実装で、DBの例外を安全な例外へ変換するテスト。実際のDBには接続しない。"""

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.exceptions import DatabaseUnavailableError
from app.features.memos.db_repository import _translate
from app.features.memos.exceptions import MemoDatabaseError
from app.features.memos.repository import DuplicateMemo


class _FakeDriverError(Exception):
    def __init__(self, sqlstate: str | None) -> None:
        super().__init__("架空の暗号文を含むメッセージ")
        self.sqlstate = sqlstate


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (IntegrityError("INSERT ...", {}, _FakeDriverError("23505")), DuplicateMemo),
        # 一意制約以外の制約違反（CHECK・外部キー）は500
        (IntegrityError("INSERT ...", {}, _FakeDriverError("23514")), MemoDatabaseError),
        (IntegrityError("INSERT ...", {}, _FakeDriverError("23503")), MemoDatabaseError),
        (OperationalError("SELECT ...", {}, _FakeDriverError("08006")), DatabaseUnavailableError),
        (OperationalError("SELECT ...", {}, ConnectionRefusedError()), DatabaseUnavailableError),
        (OperationalError("SELECT ...", {}, _FakeDriverError("40P01")), MemoDatabaseError),
    ],
)
def test_translate(error, expected):
    translated = _translate(error)

    assert type(translated) is expected
    assert "架空の暗号文" not in str(translated)

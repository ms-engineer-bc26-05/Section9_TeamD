from dataclasses import dataclass
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.features.memos.read_repository import MemoReadRepository
from app.features.memos.read_service import MemoNotFound, delete_memo, get_owned_memo

USER_ID = UUID(int=1)
OTHER_USER_ID = UUID(int=2)
MEMO_ID = UUID(int=3)
OTHER_MEMO_ID = UUID(int=4)


@dataclass(frozen=True)
class FakeStoredMemo:
    id: UUID
    user_id: UUID


def make_repository():
    return AsyncMock(spec=MemoReadRepository)


async def test_detail_returns_owned_storage_row():
    repository = make_repository()
    stored = FakeStoredMemo(MEMO_ID, USER_ID)
    repository.find_owned.return_value = stored

    assert await get_owned_memo(repository, USER_ID, MEMO_ID) is stored
    repository.find_owned.assert_awaited_once_with(USER_ID, MEMO_ID)
    repository.delete_owned.assert_not_awaited()


@pytest.mark.parametrize(
    "stored",
    [None, FakeStoredMemo(MEMO_ID, OTHER_USER_ID), FakeStoredMemo(OTHER_MEMO_ID, USER_ID)],
)
async def test_detail_rejects_missing_or_mismatched_row(stored, caplog):
    repository = make_repository()
    repository.find_owned.return_value = stored

    with pytest.raises(MemoNotFound) as error:
        await get_owned_memo(repository, USER_ID, MEMO_ID)

    assert str(error.value) == ""
    assert not caplog.records


async def test_delete_passes_both_ids_without_unscoped_lookup():
    repository = make_repository()
    repository.delete_owned.return_value = True

    assert await delete_memo(repository, USER_ID, MEMO_ID) is None
    repository.delete_owned.assert_awaited_once_with(USER_ID, MEMO_ID)
    repository.find_owned.assert_not_awaited()


async def test_delete_no_matching_row_is_not_found():
    repository = make_repository()
    repository.delete_owned.return_value = False

    with pytest.raises(MemoNotFound):
        await delete_memo(repository, USER_ID, MEMO_ID)


@pytest.mark.parametrize("operation", [get_owned_memo, delete_memo])
async def test_repository_failure_is_not_swallowed_or_logged(operation, caplog):
    repository = make_repository()
    failure = RuntimeError("synthetic DB failure")
    repository.find_owned.side_effect = failure
    repository.delete_owned.side_effect = failure

    with pytest.raises(RuntimeError) as error:
        await operation(repository, USER_ID, MEMO_ID)

    assert error.value is failure
    assert not caplog.records


async def test_failed_delete_can_be_retried():
    repository = make_repository()
    repository.delete_owned.side_effect = [RuntimeError("synthetic failure"), True, False]

    with pytest.raises(RuntimeError):
        await delete_memo(repository, USER_ID, MEMO_ID)
    await delete_memo(repository, USER_ID, MEMO_ID)
    with pytest.raises(MemoNotFound):
        await delete_memo(repository, USER_ID, MEMO_ID)

    assert repository.delete_owned.await_count == 3

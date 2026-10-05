"""メモ保存のServiceのテスト。DB・外部APIへは接続しない。テストデータはすべて架空。"""

import asyncio
import dataclasses
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import partial
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet

from app.features.consultations.public import (
    ConsultationNotFound,
    ConsultationStateConflict,
    discard_consultation,
    get_approved_result,
)
from app.features.consultations.schemas import ConsultationStatus, HandlingType
from app.features.consultations.store import ConsultationStore
from app.features.memos.crypto import MemoEncryptionError, create_fernet, decrypt_payload
from app.features.memos.repository import UserNotActive, UserNotFound
from app.features.memos.service import MemoSaveService

from tests.features.consultations.factories import make_save_confirmation_state
from tests.features.memos.fakes import InMemoryMemoRepository

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_USER_ID = UUID("22222222-2222-4222-8222-222222222222")
APPROVED_AT = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)


@pytest.fixture
def store():
    return ConsultationStore()


@pytest.fixture
def repo():
    return InMemoryMemoRepository()


@pytest.fixture
def cipher():
    return create_fernet(Fernet.generate_key().decode("ascii"))


def make_service(repo, cipher, store):
    return MemoSaveService(
        repo,
        cipher,
        get_approved=partial(get_approved_result, store=store),
        discard=partial(discard_consultation, store=store),
    )


async def test_saves_encrypted_memo_and_discards_state(repo, cipher, store):
    state = make_save_confirmation_state(
        store, USER_ID, handling=HandlingType.TELL, approved_at=APPROVED_AT
    )
    service = make_service(repo, cipher, store)

    memo, created = await service.save(USER_ID, state.consultation_id, "架空の理由")

    assert created is True
    assert memo.handling == "tell"
    assert memo.reason == "架空の理由"
    assert memo.event_summary == "架空の出来事の要約"

    row = repo.rows[(USER_ID, state.consultation_id)]
    assert row.id == memo.memo_id
    assert row.approved_at == APPROVED_AT
    assert row.save_consented_at.tzinfo is not None
    assert (row.encryption_version, row.key_version, row.payload_version) == (
        "fernet-v1",
        "v1",
        1,
    )
    # 平文が暗号文に含まれない
    for text in ("架空の出来事の要約", "架空の本音", "架空の理由"):
        assert text.encode("utf-8") not in row.encrypted_payload
    # 承認済みの結果・扱い方・理由だけを保存している
    assert decrypt_payload(
        row.encrypted_payload, user_id=USER_ID, memo_id=row.id, cipher=cipher
    ) == {
        "event_summary": "架空の出来事の要約",
        "emotion": "架空の感情",
        "true_feeling": "架空の本音",
        "background": "",
        "wish": "架空の望み",
        "handling": "tell",
        "reason": "架空の理由",
    }
    # 保存成功後は一時状態を破棄する
    assert not store.exists(USER_ID, state.consultation_id)


async def test_retry_after_save_returns_existing_memo_without_state(repo, cipher, store):
    state = make_save_confirmation_state(store, USER_ID)
    service = make_service(repo, cipher, store)
    first, _ = await service.save(USER_ID, state.consultation_id, None)

    # 一時状態は破棄済み。応答だけ届かなかった場合の再試行
    second, created = await service.save(USER_ID, state.consultation_id, "架空の別の理由")

    assert created is False
    assert second == first
    assert len(repo.rows) == 1


async def test_cannot_save_other_users_state(repo, cipher, store):
    state = make_save_confirmation_state(store, USER_ID)
    service = make_service(repo, cipher, store)

    with pytest.raises(ConsultationNotFound):
        await service.save(OTHER_USER_ID, state.consultation_id, None)

    assert repo.rows == {}
    assert store.exists(USER_ID, state.consultation_id)


async def test_cannot_save_before_handling_is_selected(repo, cipher, store):
    state = make_save_confirmation_state(store, USER_ID)
    state.status = ConsultationStatus.HANDLING_SELECTION
    state.handling = None
    service = make_service(repo, cipher, store)

    with pytest.raises(ConsultationStateConflict):
        await service.save(USER_ID, state.consultation_id, None)

    assert repo.rows == {}


async def test_commit_failure_keeps_state_for_retry(repo, cipher, store):
    state = make_save_confirmation_state(store, USER_ID)
    service = make_service(repo, cipher, store)
    repo.commit_error = RuntimeError("fake commit failure")

    with pytest.raises(RuntimeError):
        await service.save(USER_ID, state.consultation_id, None)

    # 保存済みと返さず、一時状態を残す
    assert repo.rows == {}
    assert store.exists(USER_ID, state.consultation_id)

    _, created = await service.save(USER_ID, state.consultation_id, None)
    assert created is True
    assert len(repo.rows) == 1


async def test_discard_failure_after_commit_is_still_saved(repo, cipher, store, caplog):
    state = make_save_confirmation_state(store, USER_ID)
    calls = 0

    async def failing_discard(user_id, consultation_id):
        nonlocal calls
        calls += 1
        raise RuntimeError("fake discard failure 架空")

    service = MemoSaveService(
        repo,
        cipher,
        get_approved=partial(get_approved_result, store=store),
        discard=failing_discard,
    )

    # 保存失敗とは区別し、保存済みとして返す
    first, created = await service.save(USER_ID, state.consultation_id, None)
    assert created is True
    assert len(repo.rows) == 1
    assert "架空" not in caplog.text

    # 一時状態が残っていても、再試行では既存のメモを返し、二重保存しない
    assert store.exists(USER_ID, state.consultation_id)
    second, created = await make_service(repo, cipher, store).save(
        USER_ID, state.consultation_id, None
    )
    assert created is False
    assert second == first
    assert len(repo.rows) == 1
    assert not store.exists(USER_ID, state.consultation_id)
    assert calls == 1


@pytest.mark.parametrize(
    ("status", "error"),
    [(None, UserNotFound), ("deleting", UserNotActive)],
    ids=["user-missing", "deleting"],
)
async def test_user_changed_after_auth_is_not_saved(repo, cipher, store, status, error):
    """認証後に内部ユーザーが削除された・退会処理が始まった場合（ロック後の再確認で止める）"""
    state = make_save_confirmation_state(store, USER_ID)
    service = make_service(repo, cipher, store)

    async def get_approved_then_user_changes(user_id, consultation_id):
        approved = await get_approved_result(user_id, consultation_id, store=store)
        repo.user_statuses[user_id] = status
        return approved

    service._get_approved = get_approved_then_user_changes

    with pytest.raises(error):
        await service.save(USER_ID, state.consultation_id, None)

    # INSERTへ進まず、一時状態も破棄しない
    assert repo.rows == {}
    assert store.exists(USER_ID, state.consultation_id)


async def test_concurrent_saves_create_only_one_memo(repo, cipher, store):
    state = make_save_confirmation_state(store, USER_ID)
    service = make_service(repo, cipher, store)

    results = await asyncio.gather(
        service.save(USER_ID, state.consultation_id, None),
        service.save(USER_ID, state.consultation_id, None),
    )

    assert sorted(created for _, created in results) == [False, True]
    assert results[0][0].memo_id == results[1][0].memo_id
    assert len(repo.rows) == 1


async def test_returns_memo_saved_between_check_and_lock(repo, cipher, store):
    """最初の確認の後に、別のリクエストが保存した場合（ロック後の再検索で見つける）"""
    state = make_save_confirmation_state(store, USER_ID)
    service = make_service(repo, cipher, store)
    other_request = make_service(repo, cipher, store)

    async def get_approved_then_other_saves(user_id, consultation_id):
        approved = await get_approved_result(user_id, consultation_id, store=store)
        await other_request.save(user_id, consultation_id, None)
        return approved

    service._get_approved = get_approved_then_other_saves

    memo, created = await service.save(USER_ID, state.consultation_id, None)

    assert created is False
    assert memo.memo_id == repo.rows[(USER_ID, state.consultation_id)].id
    assert len(repo.rows) == 1


class _MissInTransactionRepository(InMemoryMemoRepository):
    """トランザクション内の再検索で見つからず、一意制約で初めて重複が分かる場合を再現する"""

    @asynccontextmanager
    async def transaction(self):
        async with super().transaction() as tx:

            async def not_found(user_id, consultation_id):
                return None

            tx.find_by_consultation = not_found
            yield tx


async def test_duplicate_insert_returns_existing_memo(cipher, store):
    repo = _MissInTransactionRepository()
    state = make_save_confirmation_state(store, USER_ID)
    service = make_service(repo, cipher, store)
    other_request = make_service(repo, cipher, store)

    async def get_approved_then_other_saves(user_id, consultation_id):
        approved = await get_approved_result(user_id, consultation_id, store=store)
        await other_request.save(user_id, consultation_id, None)
        return approved

    service._get_approved = get_approved_then_other_saves

    memo, created = await service.save(USER_ID, state.consultation_id, None)

    assert created is False
    assert memo.memo_id == repo.rows[(USER_ID, state.consultation_id)].id
    assert len(repo.rows) == 1


async def test_rejects_ciphertext_moved_to_another_memo(repo, cipher, store):
    state = make_save_confirmation_state(store, USER_ID)
    service = make_service(repo, cipher, store)
    await service.save(USER_ID, state.consultation_id, None)
    key = (USER_ID, state.consultation_id)
    repo.rows[key] = dataclasses.replace(repo.rows[key], id=uuid4())

    with pytest.raises(MemoEncryptionError):
        await service.save(USER_ID, state.consultation_id, None)


async def test_rejects_ciphertext_moved_to_another_user(repo, cipher, store):
    state = make_save_confirmation_state(store, USER_ID)
    service = make_service(repo, cipher, store)
    await service.save(USER_ID, state.consultation_id, None)
    row = repo.rows.pop((USER_ID, state.consultation_id))
    repo.rows[(OTHER_USER_ID, state.consultation_id)] = dataclasses.replace(
        row, user_id=OTHER_USER_ID
    )

    with pytest.raises(MemoEncryptionError):
        await service.save(OTHER_USER_ID, state.consultation_id, None)


async def test_rejects_memo_encrypted_with_another_key(repo, cipher, store):
    state = make_save_confirmation_state(store, USER_ID)
    await make_service(repo, cipher, store).save(USER_ID, state.consultation_id, None)
    other_cipher = create_fernet(Fernet.generate_key().decode("ascii"))

    with pytest.raises(MemoEncryptionError):
        await make_service(repo, other_cipher, store).save(
            USER_ID, state.consultation_id, None
        )

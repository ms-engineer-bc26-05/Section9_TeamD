import logging
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from redis.asyncio import Redis

import app as target


FAKE_MEMO = "架空の整理メモ：落ち着いてから話したい。"
FAKE_CONVERSATION = "架空の会話原文：まだ整理できていない気持ち。"


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("MEMO_ENCRYPTION_KEY", key)
    return key


def check_no_sensitive_values(output, values):
    # 失敗時にも、検査対象の鍵や本文を表示しない。
    if any(value and value in output for value in values):
        raise AssertionError("Sensitive value detected")


@pytest_asyncio.fixture
async def client():
    # compose.yamlの検証専用DBだけを使用する。
    await target.initialize_database()

    async with target.database_connection() as connection:
        await connection.execute("DELETE FROM verification_memos")

    transport = httpx.ASGITransport(app=target.app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://verification",
    ) as test_client:
        yield test_client


async def memo_count():
    async with target.database_connection() as connection:
        return await connection.fetchval(
            "SELECT COUNT(*) FROM verification_memos"
        )


async def check_redis_empty():
    import os

    redis = Redis.from_url(
        os.environ["REDIS_URL"],
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    try:
        # 今回のアプリはRedisへ何も保存しない設計。
        assert await redis.dbsize() == 0
    finally:
        await redis.aclose()


def test_encrypt_and_decrypt():
    ciphertext = target.encrypt_memo(FAKE_MEMO)

    assert isinstance(ciphertext, bytes)
    assert ciphertext != FAKE_MEMO.encode("utf-8")
    assert FAKE_MEMO.encode("utf-8") not in ciphertext
    assert target.decrypt_memo(ciphertext) == FAKE_MEMO


def test_encryption_is_randomized():
    first = target.encrypt_memo(FAKE_MEMO)
    second = target.encrypt_memo(FAKE_MEMO)

    assert first != second
    assert target.decrypt_memo(first) == FAKE_MEMO
    assert target.decrypt_memo(second) == FAKE_MEMO


def test_modified_ciphertext_is_rejected():
    ciphertext = bytearray(target.encrypt_memo(FAKE_MEMO))
    ciphertext[len(ciphertext) // 2] ^= 1

    with pytest.raises(ValueError, match="Memo decryption failed"):
        target.decrypt_memo(bytes(ciphertext))


def test_wrong_key_is_rejected(monkeypatch):
    ciphertext = target.encrypt_memo(FAKE_MEMO)
    monkeypatch.setenv(
        "MEMO_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )

    with pytest.raises(ValueError, match="Memo decryption failed"):
        target.decrypt_memo(ciphertext)


@pytest.mark.asyncio
async def test_approved_memo_is_stored_encrypted(
    client, caplog, encryption_key
):
    caplog.set_level(logging.INFO)

    response = await client.post(
        "/verification/memos",
        json={
            "text": FAKE_MEMO,
            "approved": True,
            "save_consent": True,
        },
    )

    assert response.status_code == 201
    assert set(response.json()) == {"id"}
    memo_id = UUID(response.json()["id"])

    async with target.database_connection() as connection:
        ciphertext = await connection.fetchval(
            "SELECT ciphertext FROM verification_memos WHERE id = $1",
            memo_id,
        )
        columns = await connection.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'verification_memos'
            """
        )

    assert {row["column_name"] for row in columns} == {
        "id", "ciphertext", "created_at"
    }
    assert ciphertext != FAKE_MEMO.encode("utf-8")
    assert FAKE_MEMO.encode("utf-8") not in ciphertext
    assert target.decrypt_memo(ciphertext) == FAKE_MEMO
    assert await memo_count() == 1
    await check_redis_empty()

    check_no_sensitive_values(
        response.text + caplog.text,
        [FAKE_MEMO, encryption_key],
    )
    assert "memo_save_succeeded" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "approved,consent",
    [(False, True), (True, False), (False, False)],
)
async def test_without_approval_or_consent_is_not_saved(
    client, approved, consent, caplog, encryption_key
):
    caplog.set_level(logging.INFO)

    response = await client.post(
        "/verification/memos",
        json={
            "text": FAKE_MEMO,
            "approved": approved,
            "save_consent": consent,
        },
    )

    assert response.status_code == 400
    assert await memo_count() == 0
    await check_redis_empty()
    check_no_sensitive_values(
        response.text + caplog.text,
        [FAKE_MEMO, encryption_key],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"conversation": FAKE_CONVERSATION},
        {"approved": "true"},
        {"save_consent": 1},
        {"text": ""},
    ],
)
async def test_invalid_input_is_not_saved_or_echoed(
    client, changes, caplog, encryption_key
):
    caplog.set_level(logging.INFO)
    payload = {
        "text": FAKE_MEMO,
        "approved": True,
        "save_consent": True,
    }
    payload.update(changes)

    response = await client.post("/verification/memos", json=payload)

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}
    assert await memo_count() == 0
    await check_redis_empty()
    check_no_sensitive_values(
        response.text + caplog.text,
        [FAKE_MEMO, FAKE_CONVERSATION, encryption_key],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("key_state", ["missing", "invalid"])
async def test_key_error_does_not_save_or_leak(
    client, monkeypatch, caplog, key_state, encryption_key
):
    caplog.set_level(logging.INFO)
    if key_state == "missing":
        monkeypatch.delenv("MEMO_ENCRYPTION_KEY")
    else:
        monkeypatch.setenv("MEMO_ENCRYPTION_KEY", "invalid-test-key")

    response = await client.post(
        "/verification/memos",
        json={
            "text": FAKE_MEMO,
            "approved": True,
            "save_consent": True,
        },
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Memo storage unavailable"}
    assert await memo_count() == 0
    await check_redis_empty()
    check_no_sensitive_values(
        response.text + caplog.text,
        [FAKE_MEMO, encryption_key, "invalid-test-key"],
    )
    assert "memo_save_failed" in caplog.text


def test_request_representation_hides_text():
    payload = target.MemoRequest(
        text=FAKE_MEMO,
        approved=True,
        save_consent=True,
    )

    check_no_sensitive_values(
        repr(payload) + str(payload),
        [FAKE_MEMO],
    )

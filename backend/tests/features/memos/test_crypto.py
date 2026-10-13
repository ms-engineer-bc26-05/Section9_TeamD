import json
from uuid import UUID

import pytest
from cryptography.fernet import Fernet

from app.features.memos.crypto import (
    MemoEncryptionError,
    create_fernet,
    decrypt_payload,
    encrypt_payload,
)

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_USER_ID = UUID("22222222-2222-4222-8222-222222222222")
MEMO_ID = UUID("33333333-3333-4333-8333-333333333333")
OTHER_MEMO_ID = UUID("44444444-4444-4444-8444-444444444444")
FAKE_KEY = Fernet.generate_key().decode("ascii")
FAKE_PAYLOAD = {"event_summary": "架空のメモ", "handling": "hold"}


def test_payload_round_trips_with_matching_identity():
    cipher = create_fernet(FAKE_KEY)
    ciphertext = encrypt_payload(
        FAKE_PAYLOAD, user_id=USER_ID, memo_id=MEMO_ID, cipher=cipher
    )

    assert decrypt_payload(
        ciphertext, user_id=USER_ID, memo_id=MEMO_ID, cipher=cipher
    ) == FAKE_PAYLOAD
    assert "架空のメモ".encode("utf-8") not in ciphertext


@pytest.mark.parametrize(
    ("user_id", "memo_id"),
    [(OTHER_USER_ID, MEMO_ID), (USER_ID, OTHER_MEMO_ID)],
)
def test_payload_rejects_mismatched_identity(user_id, memo_id):
    cipher = create_fernet(FAKE_KEY)
    ciphertext = encrypt_payload(
        FAKE_PAYLOAD, user_id=USER_ID, memo_id=MEMO_ID, cipher=cipher
    )

    with pytest.raises(MemoEncryptionError):
        decrypt_payload(ciphertext, user_id=user_id, memo_id=memo_id, cipher=cipher)


def test_payload_rejects_ciphertext_tampering():
    cipher = create_fernet(FAKE_KEY)
    ciphertext = encrypt_payload(
        FAKE_PAYLOAD, user_id=USER_ID, memo_id=MEMO_ID, cipher=cipher
    )
    tampered = ciphertext[:-1] + (b"A" if ciphertext[-1:] != b"A" else b"B")

    with pytest.raises(MemoEncryptionError):
        decrypt_payload(tampered, user_id=USER_ID, memo_id=MEMO_ID, cipher=cipher)


def test_payload_rejects_a_different_key():
    ciphertext = encrypt_payload(
        FAKE_PAYLOAD,
        user_id=USER_ID,
        memo_id=MEMO_ID,
        cipher=create_fernet(FAKE_KEY),
    )

    with pytest.raises(MemoEncryptionError):
        decrypt_payload(
            ciphertext,
            user_id=USER_ID,
            memo_id=MEMO_ID,
            cipher=create_fernet(Fernet.generate_key().decode("ascii")),
        )


@pytest.mark.parametrize("key", [None, "", "invalid-key"])
def test_missing_or_invalid_key_is_rejected(key):
    with pytest.raises(MemoEncryptionError):
        create_fernet(key)


def test_payload_rejects_non_json_values():
    with pytest.raises(MemoEncryptionError):
        encrypt_payload(
            {"invalid": object()},
            user_id=USER_ID,
            memo_id=MEMO_ID,
            cipher=create_fernet(FAKE_KEY),
        )


def test_payload_rejects_invalid_envelope():
    cipher = create_fernet(FAKE_KEY)
    ciphertext = cipher.encrypt(json.dumps({"payload": {}}).encode("utf-8"))

    with pytest.raises(MemoEncryptionError):
        decrypt_payload(ciphertext, user_id=USER_ID, memo_id=MEMO_ID, cipher=cipher)

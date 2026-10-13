"""Encryption helpers for approved memo payloads."""

import json
from typing import Mapping
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken


class MemoEncryptionError(ValueError):
    """Raised when memo encryption or decryption cannot be completed safely."""


def create_fernet(key: str | None) -> Fernet:
    if not key:
        raise MemoEncryptionError("Memo encryption key is not configured")

    try:
        return Fernet(key.encode("ascii"))
    except (UnicodeEncodeError, ValueError):
        raise MemoEncryptionError("Memo encryption key is invalid") from None


def encrypt_payload(
    payload: Mapping[str, object],
    *,
    user_id: UUID,
    memo_id: UUID,
    cipher: Fernet,
) -> bytes:
    envelope = {
        "user_id": str(user_id),
        "memo_id": str(memo_id),
        "payload": dict(payload),
    }
    try:
        serialized = json.dumps(
            envelope,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise MemoEncryptionError("Memo payload is invalid") from None

    return cipher.encrypt(serialized)


def decrypt_payload(
    ciphertext: bytes,
    *,
    user_id: UUID,
    memo_id: UUID,
    cipher: Fernet,
) -> dict[str, object]:
    try:
        envelope = json.loads(cipher.decrypt(ciphertext).decode("utf-8"))
    except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError):
        raise MemoEncryptionError(
            "Memo decryption failed or memo identity did not match"
        ) from None

    if (
        not isinstance(envelope, dict)
        or set(envelope) != {"user_id", "memo_id", "payload"}
        or envelope["user_id"] != str(user_id)
        or envelope["memo_id"] != str(memo_id)
        or not isinstance(envelope["payload"], dict)
    ):
        raise MemoEncryptionError(
            "Memo decryption failed or memo identity did not match"
        )

    return envelope["payload"]

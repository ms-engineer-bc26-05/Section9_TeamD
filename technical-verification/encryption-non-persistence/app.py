import logging
import os
from contextlib import asynccontextmanager
from uuid import uuid4

import asyncpg
from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool


logger = logging.getLogger("encryption_verification")


def get_cipher():
    # 鍵は実行時の環境変数から読み込む。
    key = os.environ.get("MEMO_ENCRYPTION_KEY")
    if not key:
        raise ValueError("Encryption key is not configured")

    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeError):
        raise ValueError("Encryption key is invalid") from None


def encrypt_memo(text: str) -> bytes:
    return get_cipher().encrypt(text.encode("utf-8"))


def decrypt_memo(ciphertext: bytes) -> str:
    try:
        plaintext = get_cipher().decrypt(ciphertext)
        return plaintext.decode("utf-8")
    except (InvalidToken, UnicodeError):
        # 暗号文や復号後の本文を例外に含めない。
        raise ValueError("Memo decryption failed") from None


@asynccontextmanager
async def database_connection():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("Database is not configured")

    connection = await asyncpg.connect(
        database_url,
        timeout=5,
        command_timeout=5,
    )
    try:
        yield connection
    finally:
        await connection.close()


async def initialize_database():
    # このテーブルは、検証専用DBにだけ作成する。
    async with database_connection() as connection:
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS verification_memos (
                id UUID PRIMARY KEY,
                ciphertext BYTEA NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_database()
    yield


app = FastAPI(
    title="メモ暗号化・非保存の検証",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


class MemoRequest(BaseModel):
    # 会話全文など、定義していない項目は受け付けない。
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=10000)
    approved: StrictBool
    save_consent: StrictBool

    def __repr__(self):
        return "MemoRequest(<redacted>)"

    def __str__(self):
        return "MemoRequest(<redacted>)"


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, error):
    # 標準のエラー詳細には入力値が含まれる場合があるため、
    # 固定のメッセージだけを返す。
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid request"},
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/verification/memos", status_code=201)
async def save_memo(payload: MemoRequest):
    # 暗号化・DB接続より先に確認する。
    if not payload.approved or not payload.save_consent:
        raise HTTPException(
            status_code=400,
            detail="Approval and save consent are required",
        )

    try:
        ciphertext = encrypt_memo(payload.text)
        memo_id = uuid4()

        async with database_connection() as connection:
            await connection.execute(
                """
                INSERT INTO verification_memos (id, ciphertext)
                VALUES ($1, $2)
                """,
                memo_id,
                ciphertext,
            )
    except Exception:
        # 例外の詳細・本文・鍵・接続情報は記録しない。
        logger.error("memo_save_failed")
        raise HTTPException(
            status_code=503,
            detail="Memo storage unavailable",
        ) from None

    logger.info("memo_save_succeeded")
    return {"id": str(memo_id)}
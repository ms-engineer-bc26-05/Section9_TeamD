"""ヘルスチェックAPI。

- /health        : FastAPIが動いているか
- /health/db     : PostgreSQLへ接続できるか
- /health/redis  : Redisへ接続できるか

接続に失敗した場合は、内部情報（例外の内容・接続文字列など）を返さず、
固定のエラーを503で返す。ログにも例外の種類名だけを出す。
"""

import logging

import asyncpg
import redis.asyncio as redis
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import CONNECT_TIMEOUT_SECONDS, DATABASE_URL, REDIS_URL

logger = logging.getLogger(__name__)
router = APIRouter()


def _unavailable(code: str, message: str) -> JSONResponse:
    """接続失敗時の固定レスポンス。形式はAPI設計書（ドラフト）§3.5に合わせる。"""
    return JSONResponse(
        status_code=503,
        content={"error": {"code": code, "message": message}},
    )


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "backend"}


@router.get("/health/db")
async def health_db():
    try:
        conn = await asyncpg.connect(DATABASE_URL, timeout=CONNECT_TIMEOUT_SECONDS)
        try:
            await conn.fetchval("SELECT 1")
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001
        # 例外の内容には接続先などが含まれる可能性があるため、種類名だけを残す
        logger.warning("db health check failed: %s", type(exc).__name__)
        return _unavailable("DB_UNAVAILABLE", "データベースに接続できませんでした。")
    return {"status": "ok", "service": "db"}


@router.get("/health/redis")
async def health_redis():
    client = None
    try:
        client = redis.from_url(REDIS_URL, socket_connect_timeout=CONNECT_TIMEOUT_SECONDS)
        await client.ping()
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis health check failed: %s", type(exc).__name__)
        return _unavailable("REDIS_UNAVAILABLE", "Redisに接続できませんでした。")
    finally:
        if client is not None:
            await client.aclose()
    return {"status": "ok", "service": "redis"}
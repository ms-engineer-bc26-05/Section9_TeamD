import logging
import os

import asyncpg
import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)
app = FastAPI(title="stack-smoke-test backend")

# フロントエンド(Next.js, localhost:3000)からのアクセスのみ許可する
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@db:5432/postgres"
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")


@app.get("/health")
async def health():
    """固定文字列を返すだけのシンプルなヘルスチェック。"""
    return {"status": "ok", "message": "FastAPI is running"}


@app.get("/health/db")
async def health_db():
    """PostgreSQLへの疎通確認。"""
    try:
        conn = await asyncpg.connect(DATABASE_URL, timeout=3)
        try:
            result = await conn.fetchval("SELECT 1")
        finally:
            await conn.close()
        return {"status": "ok", "result": result}
    except Exception:  # noqa: BLE001 検証用途のため簡略化
        # 接続文字列等の内部情報が露出しないよう詳細はログのみに残す
        logger.exception("db health check failed")
        return {"status": "error", "detail": "db connection failed"}


@app.get("/health/redis")
async def health_redis():
    """Redisへの疎通確認。"""
    try:
        client = redis.from_url(REDIS_URL, socket_connect_timeout=3)
        pong = await client.ping()
        await client.aclose()
        return {"status": "ok", "pong": pong}
    except Exception:  # noqa: BLE001 検証用途のため簡略化
        logger.exception("redis health check failed")
        return {"status": "error", "detail": "redis connection failed"}

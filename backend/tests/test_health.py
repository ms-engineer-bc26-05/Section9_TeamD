"""ヘルスチェックAPIの最小テスト。

PostgreSQL・Redisへの接続はモックに置き換えるため、
DB・Redisを起動していなくても実行できる。
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routers import health

# 失敗時のレスポンス・ログに含まれてはいけない文字列（架空の値）
FAKE_SECRET = "postgresql://user:fake-secret-password@internal-host:5432/db"


async def _get(path: str):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


async def test_health_returns_ok():
    response = await _get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "backend"}


async def test_db_failure_returns_fixed_error(monkeypatch, caplog):
    async def fail_connect(*args, **kwargs):
        raise OSError(FAKE_SECRET)

    monkeypatch.setattr(health.asyncpg, "connect", fail_connect)

    response = await _get("/health/db")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DB_UNAVAILABLE"
    assert "fake-secret-password" not in response.text
    assert "fake-secret-password" not in caplog.text


async def test_redis_failure_returns_fixed_error(monkeypatch, caplog):
    class FailingClient:
        async def ping(self):
            raise ConnectionError(FAKE_SECRET)

        async def aclose(self):
            pass

    monkeypatch.setattr(health.redis, "from_url", lambda *args, **kwargs: FailingClient())

    response = await _get("/health/redis")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "REDIS_UNAVAILABLE"
    assert "fake-secret-password" not in response.text
    assert "fake-secret-password" not in caplog.text
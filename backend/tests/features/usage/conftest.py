"""利用回数制限のテスト用の共通設定。

結合テスト（実物のRedis）は、環境変数 REDIS_URL のRedisを使う。
- ローカル：docker compose の backend コンテナ内で pytest を実行すると、compose の Redis につながる
- Redisに接続できない場合はスキップする。
  ただし REQUIRE_REDIS_TESTS=true（CI）ではスキップせず失敗にする
- テストごとに新しいユーザーIDを使い、作ったキーはテストの最後に削除する（他のキーには触れない）
"""

import os
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.features.usage.limiter import UsageLimiter, usage_key

# 存在しない接続先（接続拒否がすぐ返る）
UNREACHABLE_REDIS_URL = "redis://127.0.0.1:1/0"


@pytest.fixture
def created_users() -> list[UUID]:
    return []


@pytest.fixture
async def redis_client(created_users):
    url = os.environ.get("REDIS_URL", "")
    required = os.environ.get("REQUIRE_REDIS_TESTS", "").lower() == "true"
    client = Redis.from_url(url, decode_responses=True, socket_connect_timeout=1) if url else None
    try:
        if client is None:
            raise RedisError("REDIS_URL is not set")
        await client.ping()
    except (RedisError, OSError) as exc:
        if client is not None:
            await client.aclose()
        if required:
            pytest.fail(f"結合テスト用のRedisに接続できません: {type(exc).__name__}")
        pytest.skip("結合テスト用のRedisに接続できないためスキップします")

    yield client
    if created_users:
        await client.delete(*(usage_key(user_id) for user_id in created_users))
    await client.aclose()


@pytest.fixture
def new_user(redis_client, created_users):
    """テスト用の新しいユーザーID。テストの最後にキーを削除する"""

    def make() -> UUID:
        user_id = uuid4()
        created_users.append(user_id)
        return user_id

    return make


@pytest.fixture
def make_limiter(redis_client):
    def make(period_seconds: int = 60, **kwargs) -> UsageLimiter:
        return UsageLimiter(redis_client, period_seconds, **kwargs)

    return make

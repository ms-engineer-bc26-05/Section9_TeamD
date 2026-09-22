import logging

import redis

from verify_rate_limit import (
    REDIS_HOST,
    REDIS_PORT,
    TEST_LIMIT,
    TEST_TTL_SECONDS,
    check_and_increment,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("usage_limit")


def safe_check_and_increment(client: redis.Redis, user_id: str, limit: int, ttl_seconds: int):
    """Redis障害時は「許可」扱いにして、相談を止めない（フェイルオープン）。"""
    try:
        return check_and_increment(client, user_id, limit, ttl_seconds)
    except redis.exceptions.RedisError as e:
        logger.warning(f"Redisエラーのため回数判定をスキップし、通過扱いにする: {e}")
        return None, "redis_unavailable_allowed"


if __name__ == "__main__":
    # 接続できない場合にすぐ気づけるよう、タイムアウトを短くしておく
    client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )

    count, status = safe_check_and_increment(client, "test-user-failure", TEST_LIMIT, TEST_TTL_SECONDS)
    print(f"count={count}, status={status}")
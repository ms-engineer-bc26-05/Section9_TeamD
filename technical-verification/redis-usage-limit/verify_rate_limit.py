import os

import redis

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6380"))

# 検証用の仮の値（本番の回数・期間はここでは決めない）
TEST_LIMIT = 3
TEST_TTL_SECONDS = 60

# INCRと、初回加算時のみのEXPIREを1つのLuaスクリプトにまとめ、原子的に実行する。
# こうすることで「加算はされたがEXPIREが設定される前にクラッシュ・切断が起きる」状態を防ぐ。
INCR_WITH_TTL_SCRIPT = """
local count = redis.call("INCR", KEYS[1])
if tonumber(count) == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end
return count
"""


def get_client() -> redis.Redis:
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def build_key(user_id: str) -> str:
    return f"usage_limit:{user_id}"


def atomic_increment(client: redis.Redis, key: str, ttl_seconds: int) -> int:
    """INCRとEXPIR(初回のみ)を1つのLuaスクリプトで原子的に実行する。"""
    return client.eval(INCR_WITH_TTL_SCRIPT, 1, key, ttl_seconds)


def check_and_increment(client: redis.Redis, user_id: str, limit: int, ttl_seconds: int):
    """回数を1加算し、現在の回数と判定結果を返す。"""
    key = build_key(user_id)
    count = atomic_increment(client, key, ttl_seconds)

    if count < limit:
        status = "before_limit"
    elif count == limit:
        status = "limit_reached"
    else:
        status = "over_limit"

    return count, status


def run_single_user_test(client: redis.Redis, user_id: str):
    key = build_key(user_id)
    client.delete(key)

    print(f"\n--- {user_id} の加算テスト（上限={TEST_LIMIT}） ---")
    for i in range(1, 6):
        count, status = check_and_increment(client, user_id, TEST_LIMIT, TEST_TTL_SECONDS)
        print(f"{i}回目: count={count}, status={status}")

    ttl = client.ttl(key)
    print(f"キー {key} のTTL: {ttl}秒")


def run_multi_user_test(client: redis.Redis, user_a: str, user_b: str):
    key_a = build_key(user_a)
    key_b = build_key(user_b)
    client.delete(key_a)
    client.delete(key_b)

    print(f"\n--- 複数ユーザーの分離テスト（{user_a} と {user_b} を交互に加算） ---")
    for i in range(1, 4):
        count_a, status_a = check_and_increment(client, user_a, TEST_LIMIT, TEST_TTL_SECONDS)
        count_b, status_b = check_and_increment(client, user_b, TEST_LIMIT, TEST_TTL_SECONDS)
        print(f"{i}回目: {user_a}=count:{count_a}/{status_a}  {user_b}=count:{count_b}/{status_b}")

    print(f"\n{user_a} の最終値: {client.get(key_a)}")
    print(f"{user_b} の最終値: {client.get(key_b)}")

    print("\n--- 保存されているusage_limit系キーの一覧 ---")
    for k in client.scan_iter(match="usage_limit:*"):
        print(f"{k} = {client.get(k)} (TTL={client.ttl(k)}秒)")


if __name__ == "__main__":
    client = get_client()
    print("PING:", client.ping())

    run_single_user_test(client, "test-user-1")
    run_multi_user_test(client, "test-user-1", "test-user-2")
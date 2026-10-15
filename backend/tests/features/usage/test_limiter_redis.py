"""Redisによるカウントの結合テスト（実物のRedis。テスト設計5節 RL）。

上限値・TTLは小さい値にする。テストデータのユーザーIDはテストごとに新しく作る。
"""

import asyncio
from datetime import UTC, datetime, timedelta

from app.features.usage.limiter import usage_key

LIMIT = 3


async def reserve_n(limiter, user_id, n, limit=LIMIT):
    return [await limiter.reserve(user_id, limit) for _ in range(n)]


# ---------------------------------------------------------------------------
# 加算・上限判定
# ---------------------------------------------------------------------------


async def test_first_reserve_sets_count_and_ttl(make_limiter, new_user, redis_client):
    # RL-01：初回の相談開始で回数が1になり、TTLが設定される
    user = new_user()
    reservation = await make_limiter(period_seconds=60).reserve(user, LIMIT)

    assert (reservation.allowed, reservation.counted, reservation.count) == (True, True, 1)
    assert await redis_client.hget(usage_key(user), "count") == "1"
    assert 0 < await redis_client.ttl(usage_key(user)) <= 60


async def test_can_start_until_limit_and_rejects_over_limit(make_limiter, new_user, redis_client):
    # RL-02・RL-03・RL-04：上限ちょうどの回までは開始でき、超える回は拒否する
    user = new_user()
    limiter = make_limiter()

    results = await reserve_n(limiter, user, LIMIT + 2)

    assert [r.allowed for r in results] == [True, True, True, False, False]
    assert [r.count for r in results] == [1, 2, 3, 3, 3]
    # 拒否したリクエストは加算しない（Q-31）
    assert [r.counted for r in results[LIMIT:]] == [False, False]
    assert await redis_client.hget(usage_key(user), "count") == "3"


async def test_counts_are_separated_by_user(make_limiter, new_user, redis_client):
    # RL-06：ユーザーごとに回数が独立している
    user_a, user_b = new_user(), new_user()
    limiter = make_limiter()

    for _ in range(3):
        await limiter.reserve(user_a, LIMIT)
        await limiter.reserve(user_b, LIMIT)

    assert await redis_client.hget(usage_key(user_a), "count") == "3"
    assert await redis_client.hget(usage_key(user_b), "count") == "3"


async def test_concurrent_reserves_never_exceed_limit(make_limiter, new_user, redis_client):
    # 同時に開始しても上限を超えない（判定と加算が原子的）
    user = new_user()
    limiter = make_limiter()

    results = await asyncio.gather(*(limiter.reserve(user, LIMIT) for _ in range(10)))

    assert sum(r.counted for r in results) == LIMIT
    assert await redis_client.hget(usage_key(user), "count") == str(LIMIT)
    # RL-09：TTLのないキーが残らない
    assert await redis_client.ttl(usage_key(user)) > 0


async def test_ttl_is_not_extended(make_limiter, new_user, redis_client):
    # RL-08：TTLは初回の加算時だけ設定され、2回目以降は延長されない
    user = new_user()
    limiter = make_limiter(period_seconds=60)
    await limiter.reserve(user, LIMIT)
    await redis_client.pexpire(usage_key(user), 5000)

    await limiter.reserve(user, LIMIT)

    assert await redis_client.hget(usage_key(user), "count") == "2"
    assert await redis_client.pttl(usage_key(user)) <= 5000


async def test_count_resets_after_ttl(make_limiter, new_user, redis_client):
    # RL-07：TTLが切れると回数がリセットされ、新しい期間が始まる
    user = new_user()
    limiter = make_limiter(period_seconds=1)
    first = await reserve_n(limiter, user, LIMIT)
    assert (await limiter.reserve(user, LIMIT)).allowed is False

    await asyncio.sleep(1.2)
    reservation = await limiter.reserve(user, LIMIT)

    assert (reservation.allowed, reservation.count) == (True, 1)
    assert reservation.period_id != first[0].period_id


async def test_unlimited_plan_counts_without_rejecting(make_limiter, new_user, redis_client):
    # 上限 None（無制限）：拒否せず、表示用に回数を数える
    user = new_user()
    results = await reserve_n(make_limiter(), user, 5, limit=None)

    assert all(r.allowed for r in results)
    assert await redis_client.hget(usage_key(user), "count") == "5"


async def test_limit_zero_rejects_without_creating_key(make_limiter, new_user, redis_client):
    user = new_user()
    reservation = await make_limiter().reserve(user, 0)

    assert reservation.allowed is False
    assert await redis_client.exists(usage_key(user)) == 0


async def test_redis_stores_only_count_and_period(make_limiter, new_user, redis_client):
    # Redisには回数と期間IDだけを保存する（会話内容・個人情報を保存しない）
    user = new_user()
    await make_limiter().reserve(user, LIMIT)

    stored = await redis_client.hgetall(usage_key(user))
    assert set(stored) == {"count", "period"}
    assert stored["count"] == "1"


async def test_replaces_unexpected_value_type(make_limiter, new_user, redis_client):
    # 以前の検証（#8）の形式（文字列の回数）が残っていても、新しい期間として数え直す
    user = new_user()
    await redis_client.set(usage_key(user), "5")

    reservation = await make_limiter().reserve(user, LIMIT)

    assert (reservation.allowed, reservation.count) == (True, 1)


# ---------------------------------------------------------------------------
# 戻す処理（質問③）
# ---------------------------------------------------------------------------


async def test_refund_returns_one(make_limiter, new_user, redis_client):
    user = new_user()
    limiter = make_limiter()
    await limiter.reserve(user, LIMIT)
    reservation = await limiter.reserve(user, LIMIT)

    assert await limiter.refund(reservation) is True
    assert await redis_client.hget(usage_key(user), "count") == "1"


async def test_refund_twice_returns_only_once(make_limiter, new_user, redis_client):
    # 同じ戻す処理が2回呼ばれても、2回分減らない
    user = new_user()
    limiter = make_limiter()
    await limiter.reserve(user, LIMIT)
    reservation = await limiter.reserve(user, LIMIT)

    results = await asyncio.gather(limiter.refund(reservation), limiter.refund(reservation))

    assert sorted(results) == [False, True]
    assert await redis_client.hget(usage_key(user), "count") == "1"


async def test_refund_does_not_reduce_other_consultation(make_limiter, new_user, redis_client):
    # 同時に開始した別の相談の回数を減らさない
    user = new_user()
    limiter = make_limiter()
    first, second = await asyncio.gather(limiter.reserve(user, LIMIT), limiter.reserve(user, LIMIT))

    await limiter.refund(first)

    assert await redis_client.hget(usage_key(user), "count") == "1"
    assert second.counted is True


async def test_refund_after_period_change_does_nothing(make_limiter, new_user, redis_client):
    # 加算後に期間が切り替わった場合、前の期間の分を戻しても新しい期間の回数を減らさない
    user = new_user()
    limiter = make_limiter(period_seconds=1)
    old = await limiter.reserve(user, LIMIT)
    await asyncio.sleep(1.2)
    await limiter.reserve(user, LIMIT)  # 新しい期間の1回目

    assert await limiter.refund(old) is False
    assert await redis_client.hget(usage_key(user), "count") == "1"


async def test_refund_to_zero_deletes_key(make_limiter, new_user, redis_client):
    # 戻して0になったらキーごと削除する（質問⑨の退会との競合にも対応）
    user = new_user()
    limiter = make_limiter()
    reservation = await limiter.reserve(user, LIMIT)

    await limiter.refund(reservation)

    assert await redis_client.exists(usage_key(user)) == 0


async def test_refund_after_key_deleted_does_not_recreate_key(make_limiter, new_user, redis_client):
    # 退会処理などでキーが削除された後に戻しても、キーを作り直さない
    user = new_user()
    limiter = make_limiter()
    reservation = await limiter.reserve(user, LIMIT)
    await limiter.delete_user_usage(user)

    assert await limiter.refund(reservation) is False
    assert await redis_client.exists(usage_key(user)) == 0


async def test_refund_of_rejected_request_does_nothing(make_limiter, new_user, redis_client):
    user = new_user()
    limiter = make_limiter()
    await reserve_n(limiter, user, LIMIT)
    rejected = await limiter.reserve(user, LIMIT)

    assert await limiter.refund(rejected) is False
    assert await redis_client.hget(usage_key(user), "count") == str(LIMIT)


# ---------------------------------------------------------------------------
# 利用状況の取得・退会時の削除
# ---------------------------------------------------------------------------


async def test_get_counter(make_limiter, new_user):
    user = new_user()
    limiter = make_limiter(period_seconds=60)

    empty = await limiter.get_counter(user)
    assert (empty.count, empty.resets_at) == (0, None)

    await reserve_n(limiter, user, 2)
    counter = await limiter.get_counter(user)
    assert counter.count == 2
    assert counter.resets_at is not None


async def test_delete_user_usage_is_idempotent(make_limiter, new_user, redis_client):
    user_a, user_b = new_user(), new_user()
    limiter = make_limiter()
    await limiter.reserve(user_a, LIMIT)
    await limiter.reserve(user_b, LIMIT)

    await limiter.delete_user_usage(user_a)
    await limiter.delete_user_usage(user_a)  # キーがなくても正常終了する

    assert await redis_client.exists(usage_key(user_a)) == 0
    assert await redis_client.hget(usage_key(user_b), "count") == "1"


async def test_resets_at_follows_ttl(make_limiter, new_user):
    fixed_now = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
    user = new_user()
    limiter = make_limiter(period_seconds=60, now=lambda: fixed_now)
    await limiter.reserve(user, LIMIT)

    counter = await limiter.get_counter(user)

    assert fixed_now < counter.resets_at <= fixed_now + timedelta(seconds=60)

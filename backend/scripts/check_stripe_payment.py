"""F-05（#59）テストモードでの実決済の確認（Stripe・ローカルのPostgreSQL）。

決済APIと同じサービス（CheckoutService・PaymentConfirmService）と実DBの実装を使い、
架空のユーザーで次の2つを確認する。手順・記録の形式は manual_checks/payments_test_mode.md。
  1. 成功：テスト用カードで支払うと、決済の確認で paid になり、利用権限が付く
  2. キャンセル：支払わずに戻ると pending のまま利用権限は付かない。
     Sessionが期限切れになると expired になり、もう一度購入できる

実行方法（リポジトリのルート。鍵は .env に書かず、その場で環境変数として渡す）：
  docker compose run --rm --build -e STRIPE_SECRET_KEY -e STRIPE_PRICE_ID_PREMIUM \
    backend python -m scripts.check_stripe_payment

停止条件：
  - テストモードの鍵（sk_test_・rk_test_）でなければ、Stripeを呼ぶ前に止める（クライアントで確認）
  - 確認が1つでも失敗した時点で中断する（後片付けは行う）
  - Stripeの呼び出しは合計20回まで（想定は15回）

画面に出すのは、ブラウザで開く決済画面のURLだけ。Session ID・秘密鍵・ユーザーIDは出さない。
決済画面のURLは、Issue・PR・Discord・画面共有に貼らない。
作った架空のユーザー・決済・利用権限は、終了時に削除する（--keep で残す）。
"""

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import config
from app.core.database import make_database_url
from app.features.payments.confirm import PaymentConfirmService
from app.features.payments.db_repository import SqlAlchemyPaymentRepository
from app.features.payments.exceptions import AlreadyPaid
from app.features.payments.models import PaymentRow, UserEntitlementRow
from app.features.payments.settings import load_checkout_settings
from app.features.payments.service import CheckoutService
from app.features.users.models import User
from app.integrations.stripe.client import (
    CheckoutSession,
    StripeConfigError,
    StripePrice,
    get_stripe_client,
)

MAX_STRIPE_CALLS = 20
TEST_CARD = "4242 4242 4242 4242"


class CheckFailed(Exception):
    pass


class StripeCallLimitReached(Exception):
    pass


class CountingStripe:
    """Stripeの呼び出し回数を数え、上限に達したら呼ぶ前に止める"""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.calls = 0

    def _count(self) -> None:
        if self.calls >= MAX_STRIPE_CALLS:
            raise StripeCallLimitReached
        self.calls += 1

    async def retrieve_price(self, price_id: str) -> StripePrice:
        self._count()
        return await self._inner.retrieve_price(price_id)

    async def create_checkout_session(self, **kwargs) -> CheckoutSession:
        self._count()
        return await self._inner.create_checkout_session(**kwargs)

    async def retrieve_checkout_session(self, session_id: str) -> CheckoutSession:
        self._count()
        return await self._inner.retrieve_checkout_session(session_id)

    async def expire_checkout_session(self, session_id: str) -> CheckoutSession:
        self._count()
        return await self._inner.expire_checkout_session(session_id)


def check(label: str, ok: bool) -> None:
    print(f"  {'PASS' if ok else 'FAIL'}: {label}")
    if not ok:
        raise CheckFailed(label)


def wait_for_enter(message: str) -> None:
    print()
    print(message)
    input("終わったら Enter を押してください（中断は Ctrl+C）：")


class Checker:
    def __init__(self, session_factory, stripe: CountingStripe) -> None:
        self._session_factory = session_factory
        self._stripe = stripe
        repository = SqlAlchemyPaymentRepository(session_factory)
        self._repository = repository
        self.checkout = CheckoutService(repository, stripe, load_checkout_settings())
        self.confirm = PaymentConfirmService(repository, stripe)
        self.user_ids: list[UUID] = []

    async def create_user(self) -> UUID:
        user_id = uuid4()
        async with self._session_factory() as session, session.begin():
            await session.execute(
                insert(User).values(id=user_id, firebase_uid=f"manual-check-{user_id}")
            )
        self.user_ids.append(user_id)
        return user_id

    async def is_paid(self, user_id: UUID) -> bool:
        # GET /payments/me と同じ判定
        async with self._repository.transaction() as tx:
            return await tx.has_paid_entitlement(user_id, datetime.now(UTC))

    async def cleanup(self) -> None:
        async with self._session_factory() as session, session.begin():
            for user_id in self.user_ids:
                await session.execute(delete(PaymentRow).where(PaymentRow.user_id == user_id))
                await session.execute(
                    delete(UserEntitlementRow).where(UserEntitlementRow.user_id == user_id)
                )
                await session.execute(delete(User).where(User.id == user_id))

    async def success_case(self) -> None:
        print("\n[1] 成功：テスト用カードで支払う")
        user_id = await self.create_user()
        started = await self.checkout.create_checkout(user_id, "premium")
        again = await self.checkout.create_checkout(user_id, "premium")
        check("購入ボタンを2回押しても、同じ決済画面が返る", again.session_id == started.session_id)
        result = await self.confirm.confirm(user_id)
        check("支払う前の確認は pending", result.status == "pending")
        check("支払う前は無料のまま", not await self.is_paid(user_id))

        wait_for_enter(
            "次のURLをブラウザで開き、テスト用カードで支払ってください。\n"
            f"  カード番号：{TEST_CARD}、有効期限：未来の日付、CVC：任意の3桁、名前・メール：架空のもの\n"
            "  支払い後に localhost:3000 が開けなくても問題ありません（フロントは未接続）\n"
            f"  {started.checkout_url}"
        )
        # 成功画面と同じく、URLの session_id を送って確認する
        result = await self.confirm.confirm(user_id, started.session_id)
        check("支払い後の確認は paid", result.status == "paid")
        check("有料の権限が付いた（GET /payments/me が premium）", await self.is_paid(user_id))
        calls_before = self._stripe.calls
        result = await self.confirm.confirm(user_id, started.session_id)
        check(
            "同じ session_id でもう一度確認しても paid（Stripeを呼ばない）",
            result.status == "paid" and self._stripe.calls == calls_before,
        )
        try:
            await self.checkout.create_checkout(user_id, "premium")
        except AlreadyPaid:
            check("有料になった後は、購入ボタンが409（ALREADY_PAID）", True)
        else:
            check("有料になった後は、購入ボタンが409（ALREADY_PAID）", False)

    async def cancel_case(self) -> None:
        print("\n[2] キャンセル：支払わずに戻る")
        user_id = await self.create_user()
        started = await self.checkout.create_checkout(user_id, "premium")

        wait_for_enter(
            "次のURLをブラウザで開き、支払わずに、左上の「←」（戻る）を押してください。\n"
            "  戻った先の localhost:3000 が開けなくても問題ありません\n"
            f"  {started.checkout_url}"
        )
        result = await self.confirm.confirm(user_id)
        check("キャンセル後の確認は pending", result.status == "pending")
        check("キャンセル後は無料のまま", not await self.is_paid(user_id))

        # 35分の有効期限を待つ代わりに、Stripeで期限切れにする（退会時の照合と同じ操作）
        await self._stripe.expire_checkout_session(started.session_id)
        result = await self.confirm.confirm(user_id)
        check("Sessionの期限切れ後の確認は expired", result.status == "expired")
        check("期限切れ後も無料のまま", not await self.is_paid(user_id))

        retried = await self.checkout.create_checkout(user_id, "premium")
        check("期限切れの後は、新しい決済画面で買い直せる", retried.session_id != started.session_id)
        # 確認で作った決済画面は、支払えないように期限切れにしておく
        await self._stripe.expire_checkout_session(retried.session_id)


async def main(keep: bool) -> int:
    logging.basicConfig(level=logging.WARNING)
    if "premium" not in load_checkout_settings().price_ids:
        print("中断：STRIPE_PRICE_ID_PREMIUM が設定されていません")
        return 1
    engine = create_async_engine(make_database_url(config.DATABASE_URL), hide_parameters=True)
    stripe = CountingStripe(get_stripe_client())
    checker = Checker(async_sessionmaker(bind=engine, expire_on_commit=False), stripe)
    exit_code = 1
    try:
        await checker.success_case()
        await checker.cancel_case()
        print("\nすべて PASS")
        exit_code = 0
    except CheckFailed:
        print("\n中断：上の FAIL を確認してください")
    except StripeConfigError:
        print("\n中断：STRIPE_SECRET_KEY が未設定、またはテストモードの鍵ではありません")
    except StripeCallLimitReached:
        print(f"\n中断：Stripeの呼び出しが上限（{MAX_STRIPE_CALLS}回）に達しました")
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n中断しました")
    except Exception as exc:
        # 例外のメッセージにはSession情報が含まれうるため、種類だけを出す
        print(f"\n中断：想定外のエラー（{type(exc).__name__}）")
    finally:
        print(f"Stripeの呼び出し：{stripe.calls}回（鍵の確認で送信前に止めた分を含む）")
        if keep:
            print("--keep のため、架空のユーザー・決済の行を残しました")
        else:
            await checker.cleanup()
            print("架空のユーザー・決済・利用権限を削除しました")
        await engine.dispose()
    return exit_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep", action="store_true", help="確認後も架空のユーザー・決済の行を残す")
    sys.exit(asyncio.run(main(parser.parse_args().keep)))

"""Stripe Checkout（テストモード・一回払い）の非同期クライアント。

- Stripe公式SDK（#6の技術検証と同じ stripe==15.6.1）の非同期メソッド（*_async）を使い、
  Stripeの応答待ちでワーカー全体を止めない（#6の検証コードは同期呼び出しだった）
- テストモードの秘密鍵（sk_test_・rk_test_）以外では呼び出さない（本番の鍵での誤請求を防ぐ）
- 秘密鍵・Session ID・URL・metadataは、例外メッセージやログに含めない
- 再試行はSDKに任せず（max_network_retries=0）、呼び出し側が同じidempotency keyで行う
"""

import logging
import os
from dataclasses import dataclass, field

import httpx
import stripe

logger = logging.getLogger(__name__)

# SDK（stripe）はレスポンス本文やエラーメッセージを INFO・DEBUG で、
# httpx はリクエストのURL（Session IDを含む）を INFO で出力する。
# Session情報をログへ出さないため、どちらも WARNING 以上だけにする
logging.getLogger("stripe").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# 設定値は共通の config.py ではなく、この連携の中で読み込む（他Issueとの競合を避けるため）
DEFAULT_TIMEOUT_SECONDS = 10.0
TEST_KEY_PREFIXES = ("sk_test_", "rk_test_")


class StripeClientError(Exception):
    """Stripeの呼び出しに失敗した。メッセージに秘密鍵・Session情報を含めない"""


class StripeConfigError(StripeClientError):
    """秘密鍵が未設定、またはテストモードの鍵ではない（呼び出す前に止める）"""


class StripeUnavailable(StripeClientError):
    """通信の失敗・タイムアウト・Stripe側の障害。

    Session作成では、Stripe側で作成されたかどうかが分からない。
    同じidempotency keyで再試行すれば、同じSessionが返る（重複作成されない）。
    """


class StripeSessionNotFound(StripeClientError):
    """指定したSession IDのCheckout Sessionが存在しない"""


class StripeIdempotencyInProgress(StripeClientError):
    """同じidempotency keyのリクエストを、Stripeがまだ処理している（HTTP 409）。

    少し待って同じidempotency keyで再試行すれば、最初のリクエストの結果が返る。
    """


class StripeIdempotencyMismatch(StripeClientError):
    """同じidempotency keyで、前回と異なる内容を送った（Price IDの変更など）。

    このidempotency keyでは、再試行しても成功しない。
    """


class StripeRequestFailed(StripeClientError):
    """上記以外の失敗（認証・パラメータ不正など）。再試行しても直らない"""


@dataclass(frozen=True)
class CheckoutSession:
    """Checkout Sessionのうち、作成・決済確認で使う項目だけを取り出したもの"""

    id: str = field(repr=False)
    url: str | None = field(repr=False)  # 完了・期限切れのSessionでは None
    status: str | None  # open / complete / expired
    payment_status: str | None  # paid / unpaid / no_payment_required
    amount_total: int | None
    currency: str | None
    client_reference_id: str | None = field(repr=False)
    metadata: dict[str, str] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class StripePrice:
    """Priceのうち、金額・通貨の確認に使う項目だけを取り出したもの"""

    id: str
    active: bool
    type: str | None  # one_time / recurring
    unit_amount: int | None
    currency: str | None


class StripeCheckoutClient:
    def __init__(
        self,
        secret_key: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,  # テストで差し替える
    ) -> None:
        self._secret_key = secret_key
        http_client = stripe.HTTPXClient(timeout=timeout_seconds)
        if transport is not None:
            # SDKは transport を受け取る引数を持たないため、テストのときだけ中のクライアントを差し替える
            http_client._client_async = httpx.AsyncClient(transport=transport)
        self._client = stripe.StripeClient(
            secret_key or "unset",  # 未設定のときは呼び出し前に止めるため、値は使われない
            http_client=http_client,
            max_network_retries=0,
        )

    def _check_test_key(self) -> None:
        if not self._secret_key:
            raise StripeConfigError("Stripeの秘密鍵が設定されていません")
        if not self._secret_key.startswith(TEST_KEY_PREFIXES):
            raise StripeConfigError("Stripeの秘密鍵がテストモードの鍵ではありません")

    async def create_checkout_session(
        self,
        *,
        price_id: str,
        client_reference_id: str,
        metadata: dict[str, str],
        success_url: str,
        cancel_url: str,
        idempotency_key: str,
    ) -> CheckoutSession:
        """一回払いのCheckout Sessionを作成する（数量は1）"""
        self._check_test_key()
        params = {
            "mode": "payment",
            "line_items": [{"price": price_id, "quantity": 1}],
            "client_reference_id": client_reference_id,
            "metadata": metadata,
            "success_url": success_url,
            "cancel_url": cancel_url,
        }
        try:
            session = await self._client.v1.checkout.sessions.create_async(
                params, {"idempotency_key": idempotency_key}
            )
        except stripe.StripeError as exc:
            raise _convert_error(exc, "create") from None
        logger.info("Checkout Sessionを作成しました")
        return _to_checkout_session(session)

    async def retrieve_checkout_session(self, session_id: str) -> CheckoutSession:
        """Checkout Sessionを取得する（決済状態の確認に使う）"""
        self._check_test_key()
        try:
            session = await self._client.v1.checkout.sessions.retrieve_async(session_id)
        except stripe.StripeError as exc:
            raise _convert_error(exc, "retrieve") from None
        return _to_checkout_session(session)

    async def retrieve_price(self, price_id: str) -> StripePrice:
        """Priceを取得する（金額・通貨はStripe Priceを正とする。#59）"""
        self._check_test_key()
        try:
            price = await self._client.v1.prices.retrieve_async(price_id)
        except stripe.StripeError as exc:
            raise _convert_error(exc, "retrieve_price") from None
        data = price.to_dict()
        return StripePrice(
            id=data["id"],
            active=bool(data.get("active")),
            type=data.get("type"),
            unit_amount=data.get("unit_amount"),
            currency=data.get("currency"),
        )


def _convert_error(exc: stripe.StripeError, operation: str) -> StripeClientError:
    """SDKの例外を変換する。SDKのメッセージにはリクエストの値が含まれることがあるため、
    ログには例外の種類とHTTPステータスだけを残す
    """
    logger.warning(
        "Stripeの呼び出しに失敗しました operation=%s error=%s status=%s",
        operation,
        type(exc).__name__,
        exc.http_status,
    )
    if isinstance(exc, stripe.APIConnectionError | stripe.RateLimitError) or (
        isinstance(exc, stripe.APIError) and (exc.http_status or 500) >= 500
    ):
        return StripeUnavailable("Stripeの呼び出しに失敗しました")
    if exc.http_status == 409:
        return StripeIdempotencyInProgress("同じidempotency keyのリクエストを処理中です")
    if isinstance(exc, stripe.IdempotencyError):
        return StripeIdempotencyMismatch("idempotency keyの内容が前回と異なります")
    if (
        operation == "retrieve"
        and isinstance(exc, stripe.InvalidRequestError)
        and exc.code == "resource_missing"
    ):
        return StripeSessionNotFound("Checkout Sessionが見つかりません")
    return StripeRequestFailed("Stripeの呼び出しに失敗しました")


def _to_checkout_session(session: stripe.checkout.Session) -> CheckoutSession:
    data = session.to_dict()
    return CheckoutSession(
        id=data["id"],
        url=data.get("url"),
        status=data.get("status"),
        payment_status=data.get("payment_status"),
        amount_total=data.get("amount_total"),
        currency=data.get("currency"),
        client_reference_id=data.get("client_reference_id"),
        metadata=dict(data.get("metadata") or {}),
    )


def get_stripe_client() -> StripeCheckoutClient:
    """APIで使うクライアント。テストでは dependency_overrides 等で差し替える"""
    return StripeCheckoutClient(
        secret_key=os.environ.get("STRIPE_SECRET_KEY", ""),
        timeout_seconds=float(os.environ.get("STRIPE_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)),
    )

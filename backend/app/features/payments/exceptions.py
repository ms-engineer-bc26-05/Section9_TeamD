"""決済機能の例外。

HTTPのステータス・エラーコードへの変換は、Routerを追加するときに http_errors.py で行う。
例外のメッセージに秘密鍵・Session ID・URLを含めない。
エラーコード名は#59で相談中の仮の案。
"""


class PlanNotAvailable(Exception):
    """未定義・提供停止中・Price IDが未設定のプラン（APIでは422）"""


class AlreadyPaid(Exception):
    """すでに有料の利用権限がある（APIでは409）"""


class CheckoutInProgress(Exception):
    """同じユーザーのSession作成を処理中。少し待って再試行する（APIでは409・CHECKOUT_IN_PROGRESS。仮）"""


class CheckoutNeedsReview(Exception):
    """creating の行のSessionを確認できないため、新しいSessionを作らずに止めた。

    APIの応答は CheckoutInProgress と同じ409・CHECKOUT_IN_PROGRESS（仮）にする。
    止まった行は、F-05の担当がStripeのダッシュボードで状態を確かめて片付ける（#59）。
    Session一覧での照合は後続のIssueで扱う。
    """


class PaymentConfirmationRequired(Exception):
    """支払い済みでまだ確認していないSessionがある（APIでは409・PAYMENT_CONFIRMATION_REQUIRED。仮）

    画面はこのSession IDで決済の確認（API設計6.8.8）へ進む。
    """

    def __init__(self, session_id: str) -> None:
        super().__init__("支払い済みでまだ確認していない決済があります")
        self.session_id = session_id


class PriceConfigError(Exception):
    """Stripe Priceが一回払いの有効なPriceではない、または金額・通貨がない（APIでは500）"""


class UnexpectedSessionState(Exception):
    """Stripeから想定外のSessionの状態が返った（APIでは500）"""

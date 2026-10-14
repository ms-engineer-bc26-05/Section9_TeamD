"""プラン（plans）・利用権限（user_entitlements）・決済（payments）を読み書きする入口。

DBの実装（SQLAlchemy）とModel・マイグレーションは、I-01のORM・マイグレーション基盤と
#59の結論（3つの表をF-05で作る）を受けて追加する。
それまではServiceとテストをこのProtocolに対して書き、テストではメモリ上の実装を使う。

ロックの取得順序は、ユーザー行 → 決済行とする（保存・退会・利用権限の更新とそろえる）。
Stripeの呼び出し中はトランザクションを持たない（DBロックを保持しない）。

DBの実装で確認すること：
  - 「同じユーザーの creating・pending は1件まで」を部分UNIQUE索引でも守り、
    違反（IntegrityError）は flush・commit のどちらでも DuplicateUnfinishedPayment へ変換する
  - DBの例外はメッセージにSQLのパラメータを含むため、メッセージを持たない例外へ包み直して送出する
"""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

PaymentStatus = Literal["creating", "pending", "paid", "expired", "failed"]
UNFINISHED_STATUSES: tuple[PaymentStatus, ...] = ("creating", "pending")


class UserNotFound(Exception):
    """ロック後の再確認で、内部ユーザーが存在しなかった"""


class UserNotActive(Exception):
    """ロック後の再確認で、ユーザーの status が active でなかった（退会処理中など）"""


class DuplicateUnfinishedPayment(Exception):
    """同じユーザーの creating・pending の行がすでにある（部分UNIQUE索引に違反した）"""


@dataclass(frozen=True)
class Plan:
    id: UUID
    code: str
    is_active: bool


@dataclass(frozen=True)
class CheckoutRequest:
    """Stripeへ送るSession作成の内容（DBでは payments.checkout_request のJSON。#59）。

    creating の行を作るときに1回だけ決めて保存し、同じ idempotency key で再試行するときも
    この内容をそのまま送る（環境の設定値が途中で変わっても、初回と同じ内容になる）。
    実際に送るパラメーターだけを持ち、秘密情報・相談内容は含めない。
    """

    price_id: str
    expires_at: datetime  # Sessionの有効期限。行の作成時刻＋35分
    success_url: str
    cancel_url: str
    client_reference_id: str = field(repr=False)
    metadata: dict[str, str] = field(repr=False)


@dataclass(frozen=True)
class NewPayment:
    """INSERTする行（status は creating）。金額・通貨はStripe Priceから取得した値"""

    id: UUID
    user_id: UUID
    plan_id: UUID
    idempotency_key: UUID
    amount_minor: int
    currency: str
    checkout_request: CheckoutRequest


@dataclass(frozen=True)
class StoredPayment:
    id: UUID
    user_id: UUID
    plan_id: UUID
    stripe_checkout_session_id: str | None = field(repr=False)
    idempotency_key: UUID = field(repr=False)
    status: PaymentStatus
    amount_minor: int
    currency: str
    checkout_request: CheckoutRequest
    created_at: datetime
    verified_at: datetime | None = None  # Stripeで支払い済みと確認した日時（paid の行）
    entitlement_applied_at: datetime | None = None  # 利用権限へ反映した日時


class PaymentTransaction(Protocol):
    """1回のDBトランザクション。正常に抜けたらcommit、例外ならrollbackする"""

    async def lock_user(self, user_id: UUID, *, require_active: bool = True) -> str:
        """対象のユーザー行をロックし、ロック後の status を返す

        ユーザーが存在しない場合は UserNotFound を送出する。
        require_active が True で status が active でない場合は UserNotActive を送出する。
        """

    async def has_paid_entitlement(self, user_id: UUID, now: datetime) -> bool:
        """現在有効な有料の利用権限があるか（権限の行がない場合は False。DB障害は例外）"""

    async def find_plan(self, code: str) -> Plan | None: ...

    async def find_unfinished(self, user_id: UUID) -> StoredPayment | None:
        """同じユーザーの creating・pending の行を返す（1件まで）"""

    async def insert(self, payment: NewPayment) -> StoredPayment:
        """部分UNIQUE索引に違反した場合は DuplicateUnfinishedPayment を送出する"""

    async def lock_payment(self, payment_id: UUID) -> StoredPayment | None:
        """決済行をロックして返す（ユーザー行のロックの後に呼ぶ）"""

    async def mark_pending(self, payment_id: UUID, session_id: str) -> None:
        """creating の行へSession IDを保存し、pending にする"""

    async def mark_expired(self, payment_id: UUID, verified_at: datetime) -> None: ...

    async def mark_failed(self, payment_id: UUID) -> None: ...

    async def mark_paid(self, payment_id: UUID, verified_at: datetime) -> None:
        """pending の行を paid にし、Stripeで確認した日時を記録する"""

    async def grant_entitlement(self, user_id: UUID, plan_id: UUID, now: datetime) -> None:
        """有料の利用権限を付与する（status は active、valid_until は NULL。#59）

        plans/public.py（F-03）ができたら、そこの権限付与の関数へ移す。
        """

    async def mark_entitlement_applied(self, payment_id: UUID, applied_at: datetime) -> None:
        """paid の行へ、利用権限へ反映した日時を記録する"""


class PaymentRepository(Protocol):
    async def find_unfinished(self, user_id: UUID) -> StoredPayment | None:
        """トランザクションの外で、同じユーザーの creating・pending の行を返す"""

    async def find_by_session_id(self, session_id: str) -> StoredPayment | None:
        """トランザクションの外で、Session IDの行を返す（本人かどうかは呼び出し側で確認する）"""

    async def find_confirmable(self, user_id: UUID) -> StoredPayment | None:
        """トランザクションの外で、本人の確認する決済を返す（session_id を省略した確認で使う）

        pending の行を優先し、なければ「paid だが利用権限へ未反映」の行を返す。
        creating の行は返さない（Sessionのurlがまだユーザーに渡っていないため）。
        """

    def transaction(self) -> AbstractAsyncContextManager[PaymentTransaction]: ...

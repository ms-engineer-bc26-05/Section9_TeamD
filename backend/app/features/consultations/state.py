"""相談中の一時状態。

一時状態はAPIプロセスのメモリ上だけで保持し、DB・Redis・ログへ保存しない。
相談内容を含む項目は repr=False とし、誤ってログへ出力しても本文が出ないようにする。
"""

import asyncio
import copy
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from app.features.consultations.schemas import (
    ApprovableResult,
    ConsultationResultDraft,
    ConsultationStatus,
    EmotionInput,
    EventDetailsDraft,
    HandlingType,
    SafetyGuidance,
    ThemeCategory,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class DialogueTurn:
    """AIへ渡す会話の1件。ユーザー入力は必ず role="user" に入れ、systemへ連結しない"""

    role: Literal["user", "assistant"]
    content: str = field(repr=False)


@dataclass
class ConsultationState:
    """1相談分の一時状態"""

    consultation_id: UUID
    user_id: UUID  # 所有者確認に使う（CurrentUser.user_id）
    theme: ThemeCategory
    status: ConsultationStatus
    updated_at: datetime = field(default_factory=utc_now)  # TTL（I-03B）で使う

    # AIへ渡す会話の文脈
    messages: list[DialogueTurn] = field(default_factory=list, repr=False)

    # 出来事（画面6-A・6-B）
    question_count: int = 0
    correction_count: int = 0
    ai_understanding: str | None = field(default=None, repr=False)
    ai_question: str | None = field(default=None, repr=False)
    event_details: EventDetailsDraft | None = field(default=None, repr=False)

    # 感情・本音・背景・望み（画面6-C〜6-E）
    emotion: EmotionInput | None = field(default=None, repr=False)
    guided_turn_count: int = 0  # 本音・背景・望みの回答回数（question_countとは別に数える）
    background_skipped: bool = False  # 背景の質問に「まだ分からない」と答えたか

    # 整理結果・承認・扱い方（画面7〜9）
    result: ConsultationResultDraft | None = field(default=None, repr=False)
    approved_result: ApprovableResult | None = field(default=None, repr=False)
    approved_at: datetime | None = None  # 値があれば承認済み
    handling: HandlingType | None = None

    # 安全案内（サーバー側の固定文言で正規化した値。AIの生成文は入れない）
    safety_guidance: SafetyGuidance | None = None

    # 相談IDごとのロック（グローバルロックは使わない）
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)

    @property
    def approved(self) -> bool:
        return self.approved_at is not None

    def clear_content(self) -> None:
        """安全案内へ切り替えるときなどに、相談内容を保持しないよう消去する"""
        self.messages.clear()
        self.ai_understanding = None
        self.ai_question = None
        self.event_details = None
        self.emotion = None
        self.result = None
        self.approved_result = None

    def touch(self) -> None:
        """更新に成功したときに最終操作時刻を更新する（GETでは呼ばない）"""
        self.updated_at = utc_now()

    def snapshot(self) -> dict[str, Any]:
        """更新前の値の控えをとる（ロックは除く）。

        リストは中身ごと書き換わるためコピーする。Pydanticのモデルは、更新時に
        丸ごと差し替える（model_copy）ため、参照をそのまま控えればよい。
        """
        return {
            f.name: copy.copy(getattr(self, f.name)) for f in fields(self) if f.name != "lock"
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """snapshot() でとった控えへ戻す"""
        for name, value in snapshot.items():
            setattr(self, name, value)

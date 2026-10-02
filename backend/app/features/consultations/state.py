"""相談中の一時状態。

一時状態はAPIプロセスのメモリ上だけで保持し、DB・Redis・ログへ保存しない。
相談内容を含む項目は repr=False とし、誤ってログへ出力しても本文が出ないようにする。
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from app.features.consultations.schemas import (
    ApprovableResult,
    ConsultationResultDraft,
    ConsultationStatus,
    EmotionInput,
    EventDetailsDraft,
    HandlingType,
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
    guided_turn_count: int = 0

    # 整理結果・承認・扱い方（画面7〜9）
    result: ConsultationResultDraft | None = field(default=None, repr=False)
    approved_result: ApprovableResult | None = field(default=None, repr=False)
    approved_at: datetime | None = None  # 値があれば承認済み
    handling: HandlingType | None = None

    # 相談IDごとのロック（グローバルロックは使わない）
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)

    @property
    def approved(self) -> bool:
        return self.approved_at is not None

    def touch(self) -> None:
        """更新に成功したときに最終操作時刻を更新する（GETでは呼ばない）"""
        self.updated_at = utc_now()

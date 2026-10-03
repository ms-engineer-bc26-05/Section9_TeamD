"""相談機能で使う型（Enum・Schema）。

docs/api-design.md の4章・6.2.0・10章で定義済みの型を実装する。
AI出力・ユーザー入力・サーバー管理状態を同じSchemaに混在させない（4.0）。
すべてのSchemaで extra="forbid" とし、想定外の項目を拒否する。
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------


class ThemeCategory(str, Enum):
    """相談テーマ（6.2.0）"""

    COMMUNICATION = "communication"  # 会話・連絡・愛情表現
    LIFESTYLE = "lifestyle"  # 暮らし・家事・生活習慣
    MONEY = "money"  # お金の感覚の違い
    CARE = "care"  # 気遣い・思いやりの伝わり方
    FUTURE = "future"  # 将来・価値観・二人の関係
    OTHER = "other"  # その他


class ConsultationStatus(str, Enum):
    """相談の状態（10章）"""

    EVENT_DIALOGUE = "event_dialogue"  # 画面6-A：出来事の対話・訂正中
    EVENT_SUMMARY_READY = "event_summary_ready"  # 画面6-B：要約の確認待ち
    EMOTION_SELECTION = "emotion_selection"  # 画面6-C：感情選択待ち
    GUIDED_DIALOGUE = "guided_dialogue"  # 画面6-D・6-E：本音・背景・望みの対話中
    RESULT_READY = "result_ready"  # 画面7：整理結果の確認待ち
    HANDLING_SELECTION = "handling_selection"  # 画面8：扱い方選択待ち
    SAVE_CONFIRMATION = "save_confirmation"  # 画面9：保存確認待ち
    SAFETY_GUIDANCE = "safety_guidance"  # 危機的内容を検知し安全案内を提示中


class EmotionCategory(str, Enum):
    """感情の選択肢（4.2）"""

    LONELY = "lonely"  # 寂しい
    SAD = "sad"  # 悲しい
    ANXIOUS = "anxious"  # 不安
    ANGRY = "angry"  # 怒り・いら立ち
    CONFUSED = "confused"  # モヤモヤ・違和感
    HURT = "hurt"  # 傷ついた
    SELF_BLAME = "self_blame"  # 自分を責める気持ち（情けなさ・罪悪感）
    OTHER = "other"  # その他・まだよく分からない


class GuidedTopic(str, Enum):
    """本音・背景・望みの対話で、いま質問している項目（Q-13。順序はサーバーが管理する）"""

    TRUE_FEELING = "true_feeling"  # 本音
    BACKGROUND = "background"  # 背景
    WISH = "wish"  # 望み


# 質問する順序。標準の質問数はこの長さ（3問）
GUIDED_TOPIC_ORDER = (GuidedTopic.TRUE_FEELING, GuidedTopic.BACKGROUND, GuidedTopic.WISH)


class HandlingType(str, Enum):
    """扱い方（4.4）"""

    TELL = "tell"  # 伝える
    HOLD = "hold"  # 今は保留する
    NOT_TELL = "not_tell"  # 伝えない


# ---------------------------------------------------------------------------
# 出来事の要約（4.1）
# ---------------------------------------------------------------------------


class EventDetailsDraft(BaseModel):
    """AIが生成する一次案（本人の確認前）"""

    model_config = ConfigDict(extra="forbid")

    what_happened: str = Field(max_length=500)  # 何があったか
    what_bothered_me: str = Field(max_length=500)  # 何が気になったか


class EventDetailsInput(BaseModel):
    """本人が確認・訂正・編集して送り返す内容"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    what_happened: str = Field(min_length=1, max_length=500)
    what_bothered_me: str = Field(min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# 感情の選択・具体化（4.2）
# ---------------------------------------------------------------------------


class EmotionInput(BaseModel):
    """本人が選んだ感情と、自分の言葉での具体化"""

    model_config = ConfigDict(extra="forbid")

    category: EmotionCategory
    detail: str | None = Field(default=None, max_length=300)
    cannot_verbalize: bool = False  # 「うまく言葉にできない」を選んだか

    @model_validator(mode="after")
    def check_detail_or_cannot_verbalize(self) -> "EmotionInput":
        # ValueErrorのメッセージは422ハンドラで定型文へ置き換わる想定（入力値は含めない）
        has_detail = bool(self.detail and self.detail.strip())
        if not self.cannot_verbalize and not has_detail:
            raise ValueError("detailまたはcannot_verbalizeのいずれかが必要です")
        if self.cannot_verbalize and self.detail:
            raise ValueError("cannot_verbalize=Trueの場合はdetailを指定しない")
        return self


# ---------------------------------------------------------------------------
# 整理結果（4.3）
# ---------------------------------------------------------------------------


class ConsultationResultDraft(BaseModel):
    """AIが生成する一次案（本人の確認前）"""

    model_config = ConfigDict(extra="forbid")

    event_summary: str = Field(max_length=500)  # 出来事
    emotion: str = Field(max_length=300)  # 感情
    true_feeling: str = Field(max_length=500)  # 本音
    # 背景。読み取れない場合は空文字。AIが推測で補わない
    background: str = Field(default="", max_length=500)
    wish: str = Field(max_length=500)  # 望み


class ConsultationResultInput(BaseModel):
    """本人が編集して送り返す内容（部分更新）。approvedは受け付けない"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    event_summary: str | None = Field(default=None, min_length=1, max_length=500)
    emotion: str | None = Field(default=None, min_length=1, max_length=300)
    true_feeling: str | None = Field(default=None, min_length=1, max_length=500)
    background: str | None = Field(default=None, max_length=500)
    wish: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def check_fields(self) -> "ConsultationResultInput":
        # 更新する項目を1つも含まない {} は拒否する（6.4.2）
        if not self.model_fields_set:
            raise ValueError("更新する項目がありません")
        # 送られた項目に null は認めない（空文字にできるのは background のみ）
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("nullは指定できません")
        return self


class ApprovableResult(BaseModel):
    """承認・保存の対象とする整理結果（承認時にサーバー側で検証する）"""

    # 空白のみの値も空として扱うため、検証前に前後の空白を除去する
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    event_summary: str = Field(min_length=1, max_length=500)
    emotion: str = Field(min_length=1, max_length=300)
    true_feeling: str = Field(min_length=1, max_length=500)
    background: str = Field(default="", max_length=500)  # 空文字を許容
    wish: str = Field(min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# 扱い方（4.4）
# ---------------------------------------------------------------------------


class HandlingChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handling: HandlingType


# ---------------------------------------------------------------------------
# 安全案内（4.5）
# ---------------------------------------------------------------------------


class SafetyGuidanceDraft(BaseModel):
    """AIが生成する一次案。safety_messageはバックエンドで破棄し、固定文言へ差し替える"""

    model_config = ConfigDict(extra="forbid")

    risk_detected: bool
    safety_message: str
    continued_normal_structuring: bool


class SafetyGuidance(BaseModel):
    """サーバーが正規化して返す安全案内（AI出力をそのまま返さない）"""

    model_config = ConfigDict(extra="forbid")

    risk_detected: bool
    safety_message: str  # サーバー側の固定文言
    continued_normal_structuring: bool

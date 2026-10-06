"""危機的な内容への安全案内（I-03B。Q-09）。

- AIを呼ぶ前に、明らかな危機の表現をキーワードで判定する。AIの判定（kind="safety"）の
  見逃しに備えた保険であり、網羅は目指さない
- 安全案内の文言は、サーバー側の固定文言だけを使う（AIの生成文は使わない。設計書4.5）

キーワードと文言は仮のもの。Issue #50でチームが確認した一覧・文言に差し替える。
キーワードは、それだけで危険度が高いと分かる表現に絞り、誇張でもよく使う語
（「死ぬ」「消える」単体など）は入れない。略語・隠語は意味が確定する形で登録する
（例：「タヒ」単体は「タヒチ」にも一致するため使わない）。
"""

import re
import unicodedata

from app.features.consultations.schemas import SafetyGuidance

# 危機を示すキーワード（仮）。照合の前に normalize() で表記をそろえるため、
# 全角・半角、ひらがな・カタカナ、空白の違いは登録しなくてよい
CRISIS_KEYWORDS: tuple[str, ...] = (
    "死にたい",
    "消えたい",
    "自殺",
)

# 安全案内の固定文言（仮）。相談窓口の情報は、公式ページで確認した内容だけを入れる
SAFETY_MESSAGE = "（仮）安全案内の文言は、チームで確認してから確定します。"

_WHITESPACE = re.compile(r"\s+")
# カタカナ（ァ〜ヶ）をひらがなへ変換するための差
_KATAKANA_START, _KATAKANA_END = 0x30A1, 0x30F6
_KANA_OFFSET = 0x60


def normalize(text: str) -> str:
    """照合用に表記をそろえる（全角・半角の統一、カタカナ→ひらがな、空白の除去）"""
    text = unicodedata.normalize("NFKC", text).lower()
    text = "".join(
        chr(ord(ch) - _KANA_OFFSET) if _KATAKANA_START <= ord(ch) <= _KATAKANA_END else ch
        for ch in text
    )
    return _WHITESPACE.sub("", text)


def contains_crisis_keyword(*texts: str | None) -> bool:
    """入力のどれかにキーワードが含まれるか。結果だけを返し、どの語に一致したかは返さない"""
    keywords = [normalize(k) for k in CRISIS_KEYWORDS]
    for text in texts:
        if not text:
            continue
        normalized = normalize(text)
        if any(k in normalized for k in keywords):
            return True
    return False


def fixed_safety_guidance() -> SafetyGuidance:
    """利用者へ返す安全案内。AIの出力に関係なく、常に同じ内容にする"""
    return SafetyGuidance(
        risk_detected=True,
        safety_message=SAFETY_MESSAGE,
        continued_normal_structuring=False,
    )

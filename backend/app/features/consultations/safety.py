"""危機的な内容への安全案内（I-03B。Q-09。Issue #50で決定）。

- AIを呼ぶ前に、明らかな危機の表現をキーワードで判定する。AIの判定（kind="safety"）の
  見逃しに備えた保険であり、網羅は目指さない。キーワードに該当しなくても安全とは判断しない
- キーワードは自傷・自殺に絞る。他者を傷つけるおそれ・暴力を受けている状況は、
  誇張表現が多いため、AIの判定に任せる（AIへの指示は prompts.py の COMMON_INSTRUCTIONS）
- 安全案内の文言は、サーバー側の固定文言だけを使う（AIの生成文は使わない。設計書4.5）。
  相談窓口の一覧は、画面側（I-04）の固定の定数で管理する

キーワードは、それだけで危険度が高いと分かる表現に絞り、誇張でもよく使う語
（「死ぬ」「消えたい」単体など）は入れない。略語・隠語は意味が確定する形で登録する
（例：「タヒ」単体は「タヒチ」にも一致するため使わない）。

誤検知は安全側に倒れるため許容する。既知の例：
- 否定文・引用・一般的な説明（「死にたいわけではない」「自殺対策の記事を読んだ」）
- 「遺書」：「小説の遺書の場面」にも一致する
- 「しにたい」：ひらがなで書いた「わたしにたいして」（私に対して）にも一致する
"""

import re
import unicodedata

from app.features.consultations.schemas import SafetyGuidance

# 危機を示すキーワード。照合の前に normalize() で表記をそろえるため、
# 全角・半角、ひらがな・カタカナ、空白・記号の違いは登録しなくてよい
CRISIS_KEYWORDS: tuple[str, ...] = (
    # 死にたい気持ち
    "死にたい",
    "しにたい",
    "タヒにたい",
    "氏にたい",
    "死にたくなる",
    "死んでしまいたい",
    "死のうと",
    "死ぬしかない",
    "死ぬ方法",
    "死ぬ準備",
    # 生きることへの否定
    "生きていたくない",
    "生きている意味がない",
    "生きるのをやめたい",
    # 自殺
    "自殺",
    "自死",
    "希死念慮",
    "命を絶",
    "無理心中",
    "一緒に死のう",
    "一緒に死にたい",
    "遺書",
    # 手段
    "首を吊",
    "首吊り",
    "飛び降りたい",
    "飛び降り自殺",
    "練炭",
    "オーバードーズ",
    "過剰摂取",
    "薬を大量に飲",
    # 自傷
    "自傷",
    "リストカット",
    "リスカ",
    "手首を切",
)

# 安全案内の固定文言（APIが返す短い文）。相談窓口の一覧は画面側で表示する
SAFETY_MESSAGE = (
    "ここまで話してくれて、ありがとうございます。\n"
    "とてもつらい気持ちを抱えているのかもしれません。\n"
    "安全のため、ここでの整理はいったん終わりにします。\n"
    "ひとりで抱えずに、相談窓口で話を聞いてもらうこともできますよ。"
)

_WHITESPACE = re.compile(r"\s+")
# 照合の前に取り除く文字の種類（句読点・記号。「死、に、たい」への対策）
_REMOVED_CATEGORIES = ("P", "S")
# カタカナ（ァ〜ヶ）をひらがなへ変換するための差
_KATAKANA_START, _KATAKANA_END = 0x30A1, 0x30F6
_KANA_OFFSET = 0x60


def normalize(text: str) -> str:
    """照合用に表記をそろえる（全角・半角の統一、カタカナ→ひらがな、空白・記号の除去）"""
    text = unicodedata.normalize("NFKC", text).lower()
    text = "".join(
        chr(ord(ch) - _KANA_OFFSET) if _KATAKANA_START <= ord(ch) <= _KATAKANA_END else ch
        for ch in text
        # 長音記号「ー」（Lm）は語の一部のため残す
        if not unicodedata.category(ch).startswith(_REMOVED_CATEGORIES)
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

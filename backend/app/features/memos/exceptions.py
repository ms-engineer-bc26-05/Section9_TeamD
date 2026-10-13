"""メモ機能の例外。

HTTPのステータス・エラーコードへの変換は http_errors.py で行う。
例外のメッセージに本文・鍵・暗号文を含めない。
暗号化・復号の失敗は crypto.MemoEncryptionError を使う。
"""


class MemoLimitExceeded(Exception):
    """保存済みメモの件数が、プランの保存件数の上限に達している（APIでは403）"""


class MemoDatabaseError(Exception):
    """接続障害以外のDBの失敗（APIでは500）。元の例外のメッセージは持たない"""

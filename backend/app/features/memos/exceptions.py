"""メモ機能の例外。

HTTPのステータス・エラーコードへの変換は http_errors.py で行う。
例外のメッセージに本文・鍵・暗号文を含めない。
暗号化・復号の失敗は crypto.MemoEncryptionError を使う。
"""


class MemoRepositoryUnavailable(Exception):
    """DBの実装がまだない（I-01のORM・マイグレーション基盤の後に追加する）"""

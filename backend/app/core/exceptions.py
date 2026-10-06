"""機能をまたいで使う、HTTP応答へ変換可能な専用例外。"""


class AuthenticationRequiredError(Exception):
    """認証できない、または対応する内部ユーザーが存在しない。"""


class AccountDeletingError(Exception):
    """内部ユーザーが退会処理中。"""


class AuthServiceUnavailableError(Exception):
    """認証サービスの設定・通信に問題がある。"""


class DatabaseUnavailableError(Exception):
    """呼び出し元がDB接続障害と判定した。一般のDBエラーは含めない。"""

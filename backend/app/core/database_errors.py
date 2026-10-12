"""DB操作で発生した例外から、明確な接続障害を判定する。"""

from socket import gaierror

from sqlalchemy.exc import DBAPIError, IntegrityError


_CONNECTION_SQLSTATES = {
    "08000",  # 接続例外
    "08001",  # 接続を確立できない
    "08003",  # 接続が存在しない
    "08004",  # サーバーが接続確立を拒否
    "08006",  # 接続失敗
    "57P01",  # 管理操作による停止
    "57P02",  # 障害による停止
    "57P03",  # 現在接続を受け付けられない
}


def is_database_connection_error(error: Exception) -> bool:
    """DB操作の例外だけを渡す。原因不明や制約違反は対象外。"""
    if isinstance(error, IntegrityError):
        return False

    original = error.orig if isinstance(error, DBAPIError) else error

    if isinstance(original, (ConnectionError, gaierror)):
        return True

    sqlstate = getattr(original, "sqlstate", None)
    if sqlstate is None:
        sqlstate = getattr(original, "pgcode", None)

    return isinstance(sqlstate, str) and sqlstate in _CONNECTION_SQLSTATES

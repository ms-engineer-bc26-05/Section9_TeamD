"""環境変数から設定値を読み込む。

設定値はすべて環境変数（ローカルでは .env）から渡す。
秘密情報をコードへ直接書かないこと。
"""

import os


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


# 実行環境（development / production）。ログの出し方の切り替えに使う
APP_ENV = os.environ.get("APP_ENV", "development")

# ログレベル（DEBUG / INFO / WARNING / ERROR）
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# backendコンテナから見たPostgreSQL・Redisの接続先
DATABASE_URL = os.environ.get("DATABASE_URL", "")
REDIS_URL = os.environ.get("REDIS_URL", "")

# CORSで許可するオリジン（カンマ区切り）。無制限（*）にはしない
CORS_ORIGINS = _split_csv(os.environ.get("CORS_ORIGINS", "http://localhost:3000"))

# PostgreSQL・Redisへの接続タイムアウト（秒）
CONNECT_TIMEOUT_SECONDS = 3

# 開発サーバーの自動リロード（true / false）。
# 縦断確認などで相談の一時状態を保ちたいときは false にする
BACKEND_RELOAD = os.environ.get("BACKEND_RELOAD", "true").strip().lower() != "false"
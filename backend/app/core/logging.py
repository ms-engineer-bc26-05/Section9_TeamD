"""ログの設定。

環境変数 LOG_LEVEL で出力レベルを切り替える。
相談内容・入力内容・トークン・接続文字列などはログへ出力しないこと。
"""

import logging

from app.core.config import APP_ENV, LOG_LEVEL


def setup_logging() -> None:
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)

    if APP_ENV == "production":
        # 本番用：時刻・レベル・発生元・メッセージだけを出す
        log_format = "%(asctime)s %(levelname)s %(name)s %(message)s"
    else:
        # 開発用：どのファイルの何行目かも出す
        log_format = "%(asctime)s %(levelname)s %(name)s [%(filename)s:%(lineno)d] %(message)s"

    logging.basicConfig(level=level, format=log_format, force=True)
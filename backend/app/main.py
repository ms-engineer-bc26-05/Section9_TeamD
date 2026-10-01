"""ぽろり。バックエンド（FastAPI）のエントリーポイント。

現時点ではヘルスチェックAPIだけを持つ最小構成。
認証・AI相談・メモ保存・利用回数制限・決済は後続Issueで実装する。
各機能のRouterの登録は、後続の結合Issueで行う。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import CORS_ORIGINS
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.features.health import router as health_router

setup_logging()

app = FastAPI(title="porori backend")

# 422などの共通エラーを、送信値を含まない形式で返す
register_exception_handlers(app)

# フロントエンドのオリジンだけを許可する（無制限にしない）
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    # API設計書（ドラフト）で使うメソッドとヘッダーだけを許可する
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health_router.router)
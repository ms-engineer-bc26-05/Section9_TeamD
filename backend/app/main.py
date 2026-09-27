"""ぽろり。バックエンド（FastAPI）のエントリーポイント。

現時点ではヘルスチェックAPIだけを持つ最小構成。
認証・AI相談・メモ保存・利用回数制限・決済は後続Issueで実装する。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import CORS_ORIGINS
from app.core.logging import setup_logging
from app.routers import health

setup_logging()

app = FastAPI(title="porori backend")

# フロントエンドのオリジンだけを許可する（無制限にしない）
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
)

app.include_router(health.router)
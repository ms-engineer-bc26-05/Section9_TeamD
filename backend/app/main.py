"""ぽろり。バックエンド（FastAPI）のエントリーポイント。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import CORS_ORIGINS
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.features.consultations import router as consultations_router
from app.features.health import router as health_router
from app.features.memos import read_router as memo_read_router
from app.features.memos import router as memo_router
from app.features.payments import router as payments_router
from app.features.usage import router as usage_router
from app.features.users import router as users_router

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
app.include_router(users_router.router, prefix="/api/v1")
app.include_router(consultations_router.router)
app.include_router(memo_router.router)
app.include_router(memo_read_router.router)
app.include_router(usage_router.router)
app.include_router(payments_router.router)

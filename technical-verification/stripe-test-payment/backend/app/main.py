import logging
import os

import asyncpg
import redis.asyncio as redis
import stripe
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)
app = FastAPI(title="stack-smoke-test backend")

# フロントエンド(Next.js, localhost:3000)からのアクセスのみ許可する
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],  # ← POSTを追加
    allow_headers=["*"],
)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@db:5432/postgres"
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
stripe.api_key = STRIPE_SECRET_KEY
FRONTEND_URL = "http://localhost:3000"


@app.get("/health")
async def health():
    """固定文字列を返すだけのシンプルなヘルスチェック。"""
    return {"status": "ok", "message": "FastAPI is running"}


@app.get("/health/db")
async def health_db():
    """PostgreSQLへの疎通確認。"""
    try:
        conn = await asyncpg.connect(DATABASE_URL, timeout=3)
        try:
            result = await conn.fetchval("SELECT 1")
        finally:
            await conn.close()
        return {"status": "ok", "result": result}
    except Exception:  # noqa: BLE001 検証用途のため簡略化
        logger.exception("db health check failed")
        return {"status": "error", "detail": "db connection failed"}


@app.get("/health/redis")
async def health_redis():
    """Redisへの疎通確認。"""
    try:
        client = redis.from_url(REDIS_URL, socket_connect_timeout=3)
        pong = await client.ping()
        await client.aclose()
        return {"status": "ok", "pong": pong}
    except Exception:  # noqa: BLE001 検証用途のため簡略化
        logger.exception("redis health check failed")
        return {"status": "error", "detail": "redis connection failed"}


@app.get("/api/confirm-payment")
async def confirm_payment(session_id: str):
    """Checkout Sessionの支払い状況を確認する。"""
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as e:
        logger.exception("stripe session retrieve failed")
        raise HTTPException(status_code=400, detail=str(e))

    if session.payment_status == "paid":
        return {"status": "paid"}
    else:
        return {"status": "unpaid"}

@app.post("/api/create-checkout-session")
async def create_checkout_session():
    """Stripeテストモードで買い切り型のCheckout Sessionを作成する。"""
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "jpy",
                    "product_data": {"name": "テストプラン"},
                    "unit_amount": 300,
                },
                "quantity": 1,
            }],
            success_url=f"{FRONTEND_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/cancel",
        )
        return {"url": session.url}
    except stripe.error.StripeError as e:
        logger.exception("stripe checkout session creation failed")
        raise HTTPException(status_code=400, detail=str(e))
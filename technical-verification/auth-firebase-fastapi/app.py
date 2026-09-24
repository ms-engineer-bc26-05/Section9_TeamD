import os
from functools import lru_cache

import firebase_admin
from firebase_admin import auth
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

app = FastAPI(
    title="Firebase Authentication 検証",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# 未指定の場合も、自分たちで401エラーを返せるようにする。
bearer = HTTPBearer(auto_error=False)


@lru_cache
def get_firebase_app():
    # 設定値はコードに直接書かず、実行時に渡す。
    project_id = os.environ.get("FIREBASE_PROJECT_ID")
    if not project_id:
        raise RuntimeError("Firebase project is not configured")

    # 実サービスの検証中にエミュレーター用トークンを許可しない。
    if os.environ.get("FIREBASE_AUTH_EMULATOR_HOST"):
        raise RuntimeError("Emulator is not allowed in this verification")

    return firebase_admin.initialize_app(
        options={"projectId": project_id},
        name="auth-spike",
    )


def unauthorized():
    return HTTPException(
        status_code=401,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_uid(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    if credentials is None:
        raise unauthorized()

    try:
        firebase_app = get_firebase_app()
    except Exception:
        # 設定エラーの詳細や秘密情報をレスポンスへ出さない。
        raise HTTPException(
            status_code=503,
            detail="Authentication service unavailable",
        ) from None

    try:
        decoded = auth.verify_id_token(
            credentials.credentials,
            app=firebase_app,
            check_revoked=False,
        )
    except auth.ExpiredIdTokenError:
        raise unauthorized() from None
    except auth.InvalidIdTokenError:
        raise unauthorized() from None
    except ValueError:
        raise unauthorized() from None
    except Exception:
        # 通信障害などの場合もアクセスは許可しない。
        raise HTTPException(
            status_code=503,
            detail="Authentication service unavailable",
        ) from None

    uid = decoded.get("uid")
    if not isinstance(uid, str) or not uid:
        raise unauthorized()

    return uid


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/private")
def private(uid: str = Depends(get_current_uid)):
    # トークンやUIDそのものは返さない。
    return {"authenticated": True}


def get_verification_memos():
    # 検証ユーザーAのUIDは実行時に渡す。
    owner_uid = os.environ.get("VERIFICATION_OWNER_UID")
    if not owner_uid:
        raise HTTPException(
            status_code=503,
            detail="Verification data is not configured",
        )

    # 検証用の架空データ。DBには保存しない。
    return {
        "sample-memo": {
            "owner_uid": owner_uid,
            "text": "これは認可確認用の架空メモです。",
        }
    }


@app.get("/memos/{memo_id}")
def read_memo(
    memo_id: str,
    uid: str = Depends(get_current_uid),
):
    memos = get_verification_memos()
    memo = memos.get(memo_id)

    # データの存在自体も他人へ知らせないよう、
    # 存在しない場合と所有者が違う場合は同じ404にする。
    if memo is None or memo["owner_uid"] != uid:
        raise HTTPException(
            status_code=404,
            detail="Memo not found",
        )

    return {
        "id": memo_id,
        "text": memo["text"],
    }
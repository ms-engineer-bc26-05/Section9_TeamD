import getpass
import io
import logging
import os
import time
from unittest.mock import patch

from fastapi.testclient import TestClient
from firebase_admin import auth

import verify_live as verification
from app import app, get_firebase_app

verification.MAX_REQUESTS = 3

log_buffer = io.StringIO()
forbidden = []
original_getpass = getpass.getpass


def private_input(prompt):
    value = original_getpass(prompt)
    if value:
        forbidden.append(value)
    return value


def ensure_clean(text):
    if any(value in text for value in forbidden if value):
        raise verification.VerificationStopped(
            "秘密情報または本文の混入を検出。内容は表示しません"
        )


def check_logs():
    ensure_clean(log_buffer.getvalue())
    print("PASS: 収集したINFO以上のログに検査対象の混入なし")


def main():
    api_key = os.environ.get("FIREBASE_WEB_API_KEY")
    owner_uid = os.environ.get("VERIFICATION_OWNER_UID")
    if not api_key or not owner_uid:
        raise verification.VerificationStopped("環境変数が未設定です")

    forbidden.extend([
        api_key,
        owner_uid,
        "これは認可確認用の架空メモです。",
        "-----BEGIN PRIVATE KEY-----",
    ])

    # verify_liveのログ抑止を解除し、画面ではなくメモリへ収集。
    logging.disable(logging.NOTSET)
    root = logging.getLogger()
    root.handlers = [logging.StreamHandler(log_buffer)]
    root.setLevel(logging.INFO)

    with patch.object(
        verification.HTTPAdapter, "send", verification.limited_send
    ), patch.object(getpass, "getpass", private_input):
        token, uid = verification.login("A", api_key)
        forbidden.extend([token, uid])

        if uid != owner_uid:
            raise verification.VerificationStopped(
                "ユーザーAと所有者UIDが一致しません"
            )

        firebase_app = get_firebase_app()
        decoded = auth.verify_id_token(
            token, app=firebase_app, check_revoked=False
        )
        expires_at = decoded.get("exp")
        if not isinstance(expires_at, (int, float)):
            raise verification.VerificationStopped("有効期限が不明です")

        with TestClient(app) as client:
            result = verification.check(
                client, "期限内の認証", "/private", 200, token
            )
            ensure_clean(result.text)

            verification.check(
                client, "本人の架空メモ",
                "/memos/sample-memo", 200, token
            )
            check_logs()

            remaining = max(0, expires_at + 5 - time.time())
            print(f"期限切れまで約{int(remaining / 60) + 1}分待機します。")
            print("MacとDockerを起動したままにしてください。")

            while time.time() <= expires_at + 5:
                time.sleep(min(30, max(1, expires_at + 5 - time.time())))

            try:
                auth.verify_id_token(
                    token, app=firebase_app, check_revoked=False
                )
            except auth.ExpiredIdTokenError:
                print("PASS: SDKが実トークンの期限切れを検出")
            else:
                raise verification.VerificationStopped(
                    "期限切れトークンがSDKで拒否されませんでした"
                )

            result = verification.check(
                client, "期限切れトークン", "/private", 401, token
            )
            ensure_clean(result.text)

            if result.json() != {"detail": "Authentication required"}:
                raise verification.VerificationStopped(
                    "期限切れ時のエラーレスポンスが想定外です"
                )

            check_logs()

    print("期限切れ・ログの追加検証が完了しました。")


if __name__ == "__main__":
    try:
        main()
    except verification.VerificationStopped as error:
        print(f"STOP: {error}")
    except KeyboardInterrupt:
        print("\nSTOP: 操作により中断しました")
    except Exception as error:
        print("STOP: エラーの種類:", type(error).__name__)
    finally:
        count = verification.request_count
        print(f"今回の外部通信試行数: {count}/3")
        print(f"先行検証を含む累計: {7 + count}/10")
        log_buffer.close()
import getpass
import logging
import os
from unittest.mock import patch
from urllib.parse import urlsplit

import requests
from fastapi.testclient import TestClient
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app import app

# この実行では秘密情報を含むライブラリログを出さない。
# サーバー運用時のログ確認は別途実施する。
logging.disable(logging.CRITICAL)

MAX_REQUESTS = 3
request_count = 0
original_send = HTTPAdapter.send

LOGIN_URL = (
    "https://identitytoolkit.googleapis.com/v1/"
    "accounts:signInWithPassword"
)
CERT_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/"
    "securetoken@system.gserviceaccount.com"
)


class VerificationStopped(Exception):
    pass


def limited_send(
    adapter,
    request,
    stream=False,
    timeout=None,
    verify=True,
    cert=None,
    proxies=None,
):
    """実際の外部送信を数え、再試行と送信先を制限する。"""
    global request_count

    url = urlsplit(request.url)
    destination = f"{url.scheme}://{url.netloc}{url.path}"

    allowed = (
        (request.method == "POST" and destination == LOGIN_URL)
        or (request.method == "GET" and destination == CERT_URL)
    )
    if not allowed:
        raise VerificationStopped("想定外の送信先のため停止")

    if request_count >= MAX_REQUESTS:
        raise VerificationStopped("外部リクエスト上限のため停止")

    adapter.max_retries = Retry(total=0, redirect=0)
    request_count += 1
    print(f"外部通信 {request_count}/{MAX_REQUESTS}")

    response = original_send(
        adapter,
        request,
        stream=stream,
        timeout=20,
        verify=verify,
        cert=cert,
        proxies=proxies,
    )
    if response.status_code != 200:
        raise VerificationStopped(
            f"外部サービスの応答が想定外: HTTP {response.status_code}"
        )
    return response


def login(label, api_key):
    email = getpass.getpass(f"ユーザー{label}のメールアドレス: ")
    password = getpass.getpass(f"ユーザー{label}のパスワード: ")

    response = requests.post(
        LOGIN_URL,
        params={"key": api_key},
        json={
            "email": email,
            "password": password,
            "returnSecureToken": True,
        },
        timeout=20,
        allow_redirects=False,
    )
    data = response.json()
    token = data.get("idToken")
    uid = data.get("localId")

    if not isinstance(token, str) or not token:
        raise VerificationStopped("ログイン結果にIDトークンがありません")
    if not isinstance(uid, str) or not uid:
        raise VerificationStopped("ログイン結果にUIDがありません")

    print(f"ユーザー{label}: ログイン成功")
    return token, uid


def check(client, label, path, expected_status, token=None):
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    response = client.get(path, headers=headers)

    if response.status_code != expected_status:
        raise VerificationStopped(
            f"{label}: 期待HTTP {expected_status} / "
            f"実際HTTP {response.status_code}"
        )

    if token and token in response.text:
        raise VerificationStopped("レスポンスへのトークン混入を検出")

    print(f"PASS: {label} / HTTP {response.status_code}")
    return response


def main():
    api_key = os.environ.get("FIREBASE_WEB_API_KEY")
    owner_uid = os.environ.get("VERIFICATION_OWNER_UID")

    if not api_key or not owner_uid:
        raise VerificationStopped("必要な環境変数が未設定です")

    with patch.object(HTTPAdapter, "send", limited_send):
        token_a, uid_a = login("A", api_key)

        if uid_a != owner_uid:
            raise VerificationStopped("ユーザーAと所有者UIDが一致しません")

        token_b, uid_b = login("B", api_key)

        if uid_a == uid_b:
            raise VerificationStopped("AとBに同じユーザーが入力されています")

        # Firebaseの初期化・トークン検証はモックにしない。
        with TestClient(app) as client:
            check(client, "トークン未指定", "/private", 401)

            result = check(
                client, "有効なトークン", "/private", 200, token_a
            )
            if result.json() != {"authenticated": True}:
                raise VerificationStopped("認証成功レスポンスが想定外です")

            result = check(
                client, "本人のメモ", "/memos/sample-memo", 200, token_a
            )
            if result.json() != {
                "id": "sample-memo",
                "text": "これは認可確認用の架空メモです。",
            }:
                raise VerificationStopped("本人のメモの応答が想定外です")

            check(
                client, "他人のメモ", "/memos/sample-memo", 404, token_b
            )

            # 署名の先頭を変更し、不正なトークンを作る。
            parts = token_a.split(".")
            if len(parts) != 3 or not parts[2]:
                raise VerificationStopped("トークン形式が想定外です")
            first = "A" if parts[2][0] != "A" else "B"
            parts[2] = first + parts[2][1:]
            invalid_token = ".".join(parts)

            check(
                client, "署名を改変したトークン",
                "/private", 401, invalid_token
            )

    print("今回の実接続確認は成功しました。")
    print("期限切れの実トークンと運用時ログの確認は未実施です。")


if __name__ == "__main__":
    try:
        main()
    except VerificationStopped as error:
        print(f"STOP: {error}")
    except KeyboardInterrupt:
        print("\nSTOP: 操作により中断しました")
    except Exception:
        # 例外の詳細には秘密情報が含まれる可能性がある。
        print("STOP: 想定外のエラー。詳細は表示せず停止しました")
    finally:
        print(f"今回の外部通信試行数: {request_count}/{MAX_REQUESTS}")
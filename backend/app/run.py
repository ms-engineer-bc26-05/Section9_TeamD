"""バックエンドの起動処理。

- 自動リロードの有無は環境変数 BACKEND_RELOAD で切り替える
- 相談中の一時状態をAPIプロセスのメモリで保持するため、ワーカーは1つに固定する
- アクセスログにURL等が残らないよう、アクセスログは出さない
"""

import uvicorn

from app.core.config import BACKEND_RELOAD


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=BACKEND_RELOAD,
        workers=1,
        access_log=False,
    )


if __name__ == "__main__":
    main()
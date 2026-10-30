# stack-smoke-test

候補技術(Next.js / FastAPI / PostgreSQL / Redis / Docker Compose)で、
5人が同じ開発環境を起動できるかを確認するための最小構成。
中心機能の実装は含まない。

## 構成

```
technical-verification/stack-smoke-test/
├── docker-compose.yml
├── .env.example
├── backend/          FastAPI (ヘルスチェック + DB/Redis疎通確認)
│   ├── app/main.py
│   ├── tests/test_health.py
│   ├── requirements.txt
│   └── Dockerfile
└── frontend/         Next.js (固定データを画面表示)
    ├── app/page.js
    ├── package.json
    └── Dockerfile
```

| サービス | 役割 | ホストへ公開するポート |
|---|---|---|
| frontend | Next.js。ブラウザから`/health`を呼び固定データを表示 | 3000 |
| backend  | FastAPI。ヘルスチェックとDB/Redis疎通確認APIを提供 | 8000 |
| db       | PostgreSQL 16 | なし(コンテナ間通信のみ) |
| redis    | Redis 7 | なし(コンテナ間通信のみ) |

`db`/`redis`はbackendコンテナからのみ参照するため、ホストへポートは公開していない。
`backend`は`healthcheck`により`db`/`redis`が接続可能になってから起動する(`depends_on: condition: service_healthy`)。

## 起動手順

```bash
cd technical-verification/stack-smoke-test

# 1. 環境変数ファイルを用意する(ダミー値なのでそのまま使ってよい)
cp .env.example .env

# 2. 全サービスをビルドして起動する
docker compose up --build

# 起動確認: 各コンテナがUp/healthyになっていること
docker compose ps
```

## 停止手順

```bash
# コンテナを停止(データは残す)
docker compose down

# ボリュームも含めて完全に削除したい場合
docker compose down -v
```

## 動作確認方法

1. ブラウザで `http://localhost:3000` を開く。
   → `{"status": "ok", "message": "FastAPI is running"}` を含むJSONが画面に表示されればOK。
2. PostgreSQLへの疎通確認: `http://localhost:8000/health/db` を開く。
   → `{"status": "ok", "result": 1}` が返ればOK。
3. Redisへの疎通確認: `http://localhost:8000/health/redis` を開く。
   → `{"status": "ok", "pong": true}` が返ればOK。
4. いずれかで `{"status": "error", "detail": "..."}` が返った場合は、`detail`は
   固定の要約文言のみで内部情報(接続文字列等)は含まない。詳細はbackendコンテナのログ
   (`docker compose logs backend`)で確認し、本READMEの「検証結果」欄に要約を貼り付けて記録する。

## バックエンドの最小テスト

```bash
cd backend
pip install -r requirements.txt
pytest -v
```

`test_health.py` が `/health` のレスポンス(固定文字列)を検証する。
このリポジトリ上では以下の通りパスすることを確認済み:

```
tests/test_health.py::test_health_returns_fixed_message PASSED
```

## 検証結果(実施者が追記する)

> 以下は各メンバーが実機で `docker compose up` を実行した後に埋める欄。
> 成功した場合はチェックを入れ、失敗した場合はログの要約を記載する。

- [x] `docker compose up --build` で4サービスすべて起動した
- [x] `http://localhost:3000` でFastAPIからの固定データが表示された
- [x] `/health/db` がPostgreSQLへの疎通OKを返した
- [x] `/health/redis` がRedisへの疎通OKを返した
- [x] `pytest` がパスした(1 passed)
- [x] `.env` はコミットされていない(`git status` で確認)

実施環境: macOS(Apple Silicon) / Python 3.14.6 / Docker 29.4.3(build 055a478) / Docker Compose v5.1.3
実施者: じま
実施日: 2026-09-22

補足:
- `backend/requirements.txt` の `asyncpg` はPython 3.14用wheelが存在しない `0.29.0` から `0.31.0` に変更した。
  Python 3.14環境のメンバーは同じビルドエラーを避けられる。
- `pytest` 実行時、`asyncio.iscoroutinefunction` 等のPython 3.16廃止予定に関する`DeprecationWarning`が
  52件出るが、テスト結果自体には影響なし(`1 passed`)。

失敗した場合のログ:
```
(今回は全項目成功。もし再現時に失敗した場合はここに貼り付ける)
```

### 確認担当による追加検証

- [x] `docker compose up --build` で4サービスすべて起動した(db/redisはhealthy)
- [x] `http://localhost:3000` でFastAPIからの固定データが表示された
- [x] `/health/db` がPostgreSQLへの疎通OKを返した
- [x] `/health/redis` がRedisへの疎通OKを返した
- [x] `pytest` がパスした(1 passed)
- [x] `.env` はコミットされていない(`git status`で確認、working tree clean)

実施環境: Windows / Python 3.13.14 / Docker 29.4.3(build 055a478) / Docker Compose v5.1.4
実施者: みほ
実施日: 2026-09-22

補足:
- じまさん(macOS / Python 3.14.6 / Docker Compose v5.1.3)とはOS・Pythonバージョンが異なるが、
  `asyncpg 0.31.0`指定によりビルドエラーなく再現できた。
- READMEの手順のみで別メンバー(Windows環境)でも起動・確認できることを確認済み。

## 注意事項

- 認証・AI連携・決済・暗号化・本番デプロイ・本番用インフラの決定は本検証の範囲外。
- 実装はこの検証用ディレクトリに閉じており、本番構成として採用するかは別途決定する。
- `.env` は `.gitignore` 済み。コミットするのは `.env.example`(ダミー値)のみ。
- CORSは検証用フロントエンド(`http://localhost:3000`)からの`GET`のみ許可している。他Issueで
  流用する際は許可オリジン・メソッドを必要最小限に絞ること。
- `/health/db`・`/health/redis`は接続失敗時も例外メッセージをそのまま返さず、固定の要約文言を
  返す(内部情報の露出防止)。詳細調査はbackendコンテナのログを参照する。

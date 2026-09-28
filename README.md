# Team D Final Project

Team Dの最終プロジェクト「ぽろり。」の開発用リポジトリです。

これまでの企画レビュー資料と技術検証記録は、[`issue-review/`](issue-review/)と[`technical-verification/`](technical-verification/)に保管しています。

今後の開発は、`develop`ブランチを中心に進めます。GitHubの運用ルールは[`docs/github-rules.md`](docs/github-rules.md)、AIエージェントを使うときのルールは[`AGENTS.md`](AGENTS.md)を参照してください。

## 現在の実装状況

現在は、後続の機能を実装するための**最小限のアプリ基盤**だけがある状態です（Issue #32）。

| 機能 | 状態 |
| --- | --- |
| Docker Composeでの4サービス起動（Next.js・FastAPI・PostgreSQL・Redis） | 実装済み |
| バックエンドのヘルスチェックAPI（FastAPI・PostgreSQL・Redisへの疎通確認） | 実装済み |
| フロントエンドの疎通確認画面 | 実装済み |
| Firebase Authenticationによるログイン | **未実装**（後続Issue） |
| OpenRouterを利用したAI相談 | **未実装**（後続Issue） |
| 整理メモの暗号化・保存・一覧・詳細・削除 | **未実装**（後続Issue） |
| Redisによる利用回数制限 | **未実装**（後続Issue） |
| Stripe決済・プラン反映 | **未実装**（後続Issue） |
| 退会処理 | **未実装**（後続Issue） |
| 本番用テーブル・マイグレーション・ORM | **未実装**（後続Issue） |
| デプロイ設定 | **未実装** |

## 採用技術

| 領域 | 技術 | バージョン |
| --- | --- | --- |
| フロントエンド | Next.js（App Router）/ TypeScript | Next.js 16.3.6 / React 19.3.0 / TypeScript 5.9.3 |
| フロントエンドの実行環境 | Node.js | 22（Dockerイメージ `node:22-slim`） |
| バックエンド | FastAPI / Python | FastAPI 0.115.0 / Python 3.12（Dockerイメージ `python:3.12-slim`） |
| データベース | PostgreSQL | 16 |
| キャッシュ | Redis | 7 |
| 開発環境 | Docker Compose | ― |
| テスト | pytest | 8.3.2 |

採用の理由や比較結果は、[`docs/技術選定.md`](docs/技術選定.md)を参照してください。

## ディレクトリ構成

```text
frontend/                Next.jsのアプリ
  app/                   画面（現在は疎通確認画面のみ）
backend/                 FastAPIのアプリ
  app/
    main.py              エントリーポイント・CORS設定
    core/config.py       環境変数の読み込み
    core/logging.py      ログの設定
    routers/health.py    ヘルスチェックAPI
  tests/                 バックエンドのテスト
compose.yaml             Docker Composeの設定
.env.example             環境変数の見本（ダミー値）
technical-verification/  技術検証の成果物（Issue #3〜#8）。実装からは参照しない
```

## 必要なもの

- Docker Desktop（Docker Compose v2を含むもの）
- Git

PCにNode.jsやPythonをインストールする必要はありません。すべてDockerのコンテナの中で動きます。

## 初回セットアップ

リポジトリのルートで実行します。

**1. `.env` を作る**

`.env.example` をコピーして `.env` を作ります。中身は開発用のダミー値なので、そのまま使えます。

```bash
# macOS / Linux / Git Bash
cp .env.example .env
```

```powershell
# Windows（PowerShell）
Copy-Item .env.example .env
```

`.env` は `.gitignore` に入っているため、Gitには登録されません。**本物のAPIキーやパスワードを `.env.example` に書かないでください。**

**2. Docker Desktopを起動する**

Docker Desktopを起動し、「Engine running」になるまで待ちます。

## 起動・停止

**起動**

```bash
docker compose up --build
```

初回はイメージの作成に数分かかります。このコマンドを実行したターミナルにはログが流れ続けるので、閉じずにそのままにしておきます。以降の操作は、別のターミナルで行います。

次のログが出ていれば起動しています。

- `db-1`：`database system is ready to accept connections`
- `redis-1`：`Ready to accept connections`
- `backend-1`：`Application startup complete.`
- `frontend-1`：`Ready in ...`

**停止**

ログが流れているターミナルで `Ctrl + C` を押すか、別のターミナルで次を実行します。

```bash
docker compose down
```

DBのデータ（Dockerのボリューム）も消して初期状態に戻したい場合は、`docker compose down -v` を使います。

## 疎通確認

起動したら、ブラウザで次を開きます。

| URL | 確認できること |
| --- | --- |
| http://localhost:3000 | 疎通確認画面。バックエンド・データベース・Redisの3つが「成功」と表示される |
| http://localhost:8000/health | `{"status":"ok","service":"backend"}` |
| http://localhost:8000/health/db | `{"status":"ok","service":"db"}` |
| http://localhost:8000/health/redis | `{"status":"ok","service":"redis"}` |

接続に失敗した場合、APIは内部情報を含まない固定のエラーを503で返します。

```json
{"error":{"code":"REDIS_UNAVAILABLE","message":"Redisに接続できませんでした。"}}
```

## テスト・ビルド

コンテナを起動した状態で、別のターミナルから実行します。

**バックエンドのテスト**

```bash
docker compose exec backend pytest -v -p no:cacheprovider
```

テストはPostgreSQL・Redisへの接続をモックに置き換えているため、DB・Redisの状態に関係なく実行できます。

**フロントエンドのビルド**

```bash
docker compose run --rm --no-deps frontend npm run build
```

一時的なコンテナで実行するため、起動中の開発サーバーには影響しません。

**脆弱性チェック**

```bash
docker compose run --rm --no-deps frontend npm audit
```

**コンテナの中に入って作業する場合**

```bash
docker compose exec backend bash    # バックエンド
docker compose exec frontend bash   # フロントエンド
exit                                # コンテナから出る
```

## 開発時の注意

- **保存すると自動で反映されます。** `frontend/` と `backend/` のソースコードはコンテナにつながっているため、ファイルを保存すると開発サーバーが再読み込みします。
- **Windowsでも反映されるように、ファイルの変更を定期的に確認する設定（ポーリング）を入れています。** Next.js 16の標準（Turbopack）ではこの設定が効かないため、開発サーバーは `next dev --webpack` で起動しています。本番用のビルド（`npm run build`）は標準のままです。
- **パッケージを追加・変更したときは、イメージを作り直します。** `package.json`・`package-lock.json`・`requirements.txt` を変えたときは、次を実行してください。`-V` は、古い `node_modules` を使い回さないための指定です。

  ```bash
  docker compose up --build -V
  ```

- **パッケージの追加・更新は、事前にチームへ相談します**（`AGENTS.md` のルール）。
- **ログ・エラーに、相談内容・入力内容・トークン・接続文字列を出さないでください。** ログのレベルは `.env` の `LOG_LEVEL`、開発用・本番用の出し方は `APP_ENV` で切り替えます。
- **CORS**は `.env` の `CORS_ORIGINS` に書いたURLだけを許可しています。無制限（`*`）にはしないでください。
- PostgreSQL・Redisのポートは、PC側には公開していません（コンテナ間の通信だけで使います）。

## うまく動かないとき

| 症状 | 確認すること |
| --- | --- |
| 起動時に「.envがありません」と表示される | 「初回セットアップ」の手順で `.env` を作ってください |
| `port is already allocated` と表示される | 3000番または8000番のポートを、ほかのアプリや `technical-verification/` の検証用コンテナが使っています。使っているものを停止してください |
| 疎通確認画面が「失敗」になる | `docker compose ps` で4つのサービスが `Up` になっているか確認してください。`docker compose logs backend --tail 20` でバックエンドのログを確認できます |
| Redisを止めると、データベースまで「失敗」になる | Redisのコンテナを止めている間は、名前の解決に時間がかかり、同時に行うDBの確認がタイムアウトすることがあります。`http://localhost:8000/health/db` を単体で開くと「ok」になります |
| ファイルを保存しても画面が変わらない | ブラウザを再読み込みしてください。それでも変わらない場合は `docker compose restart frontend` を実行してください |
| `docker` コマンドでServer側のエラーが出る | Docker Desktopが起動しきっていません。「Engine running」になるまで待ってください |

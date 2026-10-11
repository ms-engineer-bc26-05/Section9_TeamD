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
| Formatter・Lint | Ruff（バックエンド）/ ESLint・Prettier（フロントエンド） | Ruff 0.16.10 / ESLint 9.39.5 / Prettier 3.9.9 |

採用の理由や比較結果は、[`docs/技術選定.md`](docs/技術選定.md)を参照してください。

## ディレクトリ構成

```text
frontend/                  Next.jsのアプリ
  app/                     画面（現在は疎通確認画面のみ）
backend/                   FastAPIのアプリ
  app/
    main.py                エントリーポイント・CORS設定・共通エラーハンドラの登録
    run.py                 起動処理（自動リロードの切り替え・ワーカー数1）
    core/                  全機能で使う共通処理
      config.py            環境変数の読み込み
      errors.py            共通エラーハンドラ（422・400）
      logging.py           ログの設定
    features/              機能ごとのRouter・Schema・Service・Model
      health/router.py     ヘルスチェックAPI
    integrations/          外部サービスとの連携（Firebase・OpenRouterなど）
  tests/                   バックエンドのテスト（app/と同じ構成で配置）
compose.yaml               Docker Composeの設定
.env.example               環境変数の見本（ダミー値）
technical-verification/    技術検証の成果物（Issue #3〜#8）。実装からは参照しない
```

バックエンドは機能別の構成です（Issue #33で決定）。後続Issueで、次のフォルダ・ファイルを追加していきます。

| フォルダ・ファイル | 内容 | 担当Issue |
| --- | --- | --- |
| `core/database.py` | DB接続・セッション | I-01 |
| ORM・マイグレーションの共通基盤 | ORMの共通設定、マイグレーションの設定、ユーザー用の初期マイグレーション（配置はI-01で決定） | I-01 |
| `features/auth/` | 認証（`get_current_user` など、`dependencies.py`） | I-01 |
| `features/users/` | 内部ユーザー（`/users/me`） | I-01 |
| `features/consultations/` | AI相談・一時状態 | I-03 |
| `features/memos/` | 整理メモの保存・一覧・詳細・削除、メモ用のModel・追加マイグレーション | I-05 |
| `integrations/firebase/` | Firebase Authentication | I-01 |
| `integrations/openrouter/` | OpenRouter | I-03 |

- 各機能フォルダには、必要に応じて `router.py`・`schemas.py`・`service.py`・`models.py` などを置きます。
- 各機能のIssueでは、原則として自分の担当フォルダの中だけを変更します。上の表で担当Issueが決まっている共通部分（`core/database.py`・ORM・マイグレーションの共通基盤など）は、そのIssueで作成します。
- `requirements.txt`・`compose.yaml`・`.env.example` などの共通設定ファイルを変更する場合は、関係するIssueの担当者と確認してから進めます。
- `main.py` への各機能Routerの登録は、後続の結合Issueで行います。
- ほかの機能の内部状態やModelを直接操作せず、相手のServiceを通して利用します。

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

**自動リロードなしで起動する（縦断確認・デモ用）**

自動リロードがオンのままだと、ファイルを保存したときにバックエンドが再起動し、相談の一時状態が消えます。縦断シナリオの確認やデモでは、自動リロードをオフにして起動します。

1. `.env` の末尾に次の1行を追加します（すでにある場合は値を `false` にします）。

```
BACKEND_RELOAD=false
```

2. 起動中の場合は `Ctrl + C` で止め、もう一度起動します。

```bash
docker compose up
```

3. `backend-1` のログに `Started reloader process` が出ていなければ、自動リロードはオフです。

確認が終わったら、`.env` の `BACKEND_RELOAD` を `true` に戻すか行を削除し、もう一度起動し直します。

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

Pull Requestでは、GitHub Actionsが次のチェックを自動実行します。

- バックエンド：pytest、整形の確認（`ruff format --check`）、Lint（`ruff check`）
- フロントエンド：ビルド、整形の確認（`prettier --check .`）、Lint（`eslint . --max-warnings 0`）

ローカルでは、コンテナを起動した状態で、別のターミナルから実行します。

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

**整形・Lint**

チェックだけ行う（ファイルは書き換えない）：

```bash
docker compose exec backend ruff format --check                      # バックエンドの整形
docker compose exec backend ruff check                               # バックエンドのLint
docker compose run --rm --no-deps frontend npm run format:check      # フロントエンドの整形
docker compose run --rm --no-deps frontend npm run lint              # フロントエンドのLint
```

整形・自動修正する（ファイルを書き換える）：

```bash
docker compose exec backend ruff check --fix                         # バックエンドのLintの自動修正（importの並べ替えなど）
docker compose exec backend ruff format                              # バックエンドの整形（--fixのあとに実行する）
docker compose run --rm --no-deps frontend npm run format            # フロントエンドの整形
```

設定は、`backend/ruff.toml`、`frontend/eslint.config.mjs`、`frontend/.prettierrc.json`にあります。1行の長さは、どちらも100文字です。

ESLintは、warningも1件あればエラーとして扱います（`--max-warnings 0`）。どうしても対応できない箇所は、`// eslint-disable-next-line ルール名 -- 理由`のように、理由を書いて個別に対象外にします。指摘の原因を直したら、`eslint-disable`のコメントも消してください（使われていないコメントもwarningになり、CIが失敗します）。

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

- **保存すると自動で反映されます。** `frontend/` と `backend/` のソースコードはコンテナにつながっているため、ファイルを保存すると開発サーバーが再読み込みします。バックエンドの自動リロードは、`.env` の `BACKEND_RELOAD`（`true` / `false`）で切り替えられます（「自動リロードなしで起動する」を参照）。
- **相談中の一時状態は、バックエンドのメモリだけに保持します**（Issue #33で決定）。会話全文・入力原文・未承認の内容はDB・Redis・ログへ保存しません。そのため、バックエンドの再起動・自動リロード・一定時間の経過で一時状態は消え、ブラウザを再読み込みしても相談は復帰しません。APIはワーカー1つで起動しています（`backend/app/run.py`）。相談の途中で急に404になった場合は、バックエンドが再読み込みされた可能性があります。
- **Windowsでも反映されるように、ファイルの変更を定期的に確認する設定（ポーリング）を入れています。** Next.js 16の標準（Turbopack）ではこの設定が効かないため、開発サーバーは `next dev --webpack` で起動しています。本番用のビルド（`npm run build`）は標準のままです。
- **パッケージを追加・変更したときは、イメージを作り直します。** `package.json`・`package-lock.json`・`requirements.txt` を変えたときは、次を実行してください。`-V` は、古い `node_modules` を使い回さないための指定です。

  ```bash
  docker compose up --build -V
  ```

- **パッケージの追加・更新は、事前にチームへ相談します**（`AGENTS.md` のルール）。
- **ログ・エラーに、相談内容・入力内容・トークン・接続文字列を出さないでください。** ログのレベルは `.env` の `LOG_LEVEL`、開発用・本番用の出し方は `APP_ENV` で切り替えます。
- **入力の検証エラーは、共通のエラーハンドラ（`backend/app/core/errors.py`）で返します。** FastAPI標準の422は送信された値をそのまま含むため、送信値を含まない `{"error": {"code": "VALIDATION_ERROR", ...}}` の形式に置き換えています（API設計 §3.5）。JSONの形式そのものが壊れている場合は400（`INVALID_REQUEST`）を返します。各APIで独自の422レスポンスを作らず、このハンドラに任せてください。
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

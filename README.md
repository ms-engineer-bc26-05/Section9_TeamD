# ぽろり。

「ぽろり。」は、AIとの対話を通して気持ちを整理し、利用者自身が次の扱い方を選ぶためのWebアプリです。

- 伝える
- 今は保留する
- 伝えない

会話全文を残すのではなく、本人が内容を確認・承認し、保存に同意した整理メモだけを暗号化して保存します。

企画レビュー資料と技術検証記録は [`issue-review/`](issue-review/) と [`technical-verification/`](technical-verification/) に保管しています。画面仕様は [`docs/screen-design.md`](docs/screen-design.md)、API契約は [`docs/api-design.md`](docs/api-design.md)、テスト観点は [`docs/test-design.md`](docs/test-design.md) を参照してください。

## 主な機能

| 機能 | 現在の状態 |
| --- | --- |
| Firebase Authenticationによる新規登録・ログイン | 実装済み・実接続確認済み |
| 利用前の注意表示 | 実装済み・実画面確認済み |
| AIとの段階的な相談 | 実装済み・実API確認済み |
| 整理結果の確認・編集・承認 | 実装済み・実画面確認済み |
| 「伝える・今は保留する・伝えない」の選択 | 実装済み・実画面確認済み |
| 保存する／保存せず終了 | 実装済み・実DB確認済み |
| 保存メモの一覧・詳細・削除 | 実装済み・実画面確認済み |
| 利用回数・保存件数・プランの表示 | 実装済み・実画面確認済み |
| Stripeテストモードの一回払い | Checkout遷移・キャンセル・決済成功後の有料反映を確認済み |
| 安全案内への切り替え | 実装済み。自動テストで確認し、実APIでは一部の観点のみ確認（暴力を受けている状況の読み取りは既知の制約） |
| 退会 | バックエンドAPIは実装済み。設定画面、ログアウト・退会導線、外部サービスを含む実運用確認は未実装・未確認 |
| デプロイ、監視、バックアップ、鍵ローテーション | 未実装 |

CI成功、自動テスト、実API、実DB、実画面の確認は同じ意味ではありません。最新の縦断・異常系確認結果は、Issue #62と関連するテスト結果ドキュメントを参照してください。

## 利用の流れ

1. 新規登録またはログイン
2. 利用前の注意を確認
3. 出来事・感情・本音・背景・望みをAIとの対話で整理
4. 整理結果を本人が確認・編集し、内容を承認
5. 「伝える・今は保留する・伝えない」から扱い方を選択
6. 保存するか、保存せず終了するかを本人が選択
7. 保存した場合は、一覧・詳細の確認と削除が可能

デモ用の詳しい操作順と説明内容は [`docs/app-review/demo-script.md`](docs/app-review/demo-script.md) にまとめています。

## データの取り扱い

### 相談中

- 相談中の一時状態は、APIサーバーのメモリだけに保持します。
- 会話全文、入力原文、未承認のAI生成内容は、PostgreSQL・Redis・ブラウザストレージへ永続保存しません。
- 相談完了・中断・一定時間の経過、またはAPIサーバーの再起動で一時状態を破棄します。
- この方式のため、APIは1ワーカーで起動します。縦断確認やデモでは `BACKEND_RELOAD=false` を使用します。

### 保存時

- 本人が確認・承認し、保存に同意した整理メモだけを保存します。
- 整理メモはFernetで暗号化してPostgreSQLへ保存します。
- 保存メモはログインした本人だけが取得・削除できます。
- 保存済みメモを更新するAPIはありません。
- 保存件数の上限は、MVPでは無料10件・有料100件です。有料100件はテスト用の暫定値です。

### Redis

- Redisには相談内容を保存せず、利用回数と集計期間の管理だけに使用します。
- Redis障害時は利用回数を判定できないため、相談開始を許可し、その回を数えないフェイルオープン方式です。
- 相談の途中で中断した場合や、途中でAIが失敗した場合も、その相談は利用回数に数えられます。回数を戻すのは、開始に失敗した場合、開始時に中断した場合、開始時に安全案内へ切り替わった場合だけです。
- 現在のCompose設定ではRedisデータを永続ボリュームへ保存していないため、Redisの再作成・再起動による利用回数データの扱いは既知の制約です。

### AI

- OpenRouter経由で `openai/gpt-oss-120b` を使用します。
- ZDRかつ、学習・データ収集に利用しない提供元だけを使用する条件で接続します。
- 1回の処理上限は30秒です。条件を満たす失敗は1回だけ自動再試行し、最長待機は約56秒です。30秒のタイムアウト自体は自動再試行の対象外です。
- 推論に20〜30秒かかる場合があり、まれにタイムアウトして502 `AI_UNAVAILABLE` となることがあります。その場合は画面から再試行する設計です（画面での確認はIssue #62では未実施）。
- AIの質問の自然さ、文の途切れ、安全案内の判定を完全に保証するものではありません。

### Stripe

- Stripeはテストモードの一回払いとして実装しています。
- アプリはカード情報を保持しません。
- Checkout成功画面への復帰後に有料状態を反映します。Webhookによる非同期確定、サブスクリプション、返金はMVPの対象外です。
- 決済完了後、成功画面へ戻る前にタブを閉じた場合は直ちに有料状態へ反映されません。再度「購入手続きに進む」を選ぶと、既存の決済を確認して有料状態へ反映できることを実画面で確認しています。
- 上記の確認では、新しいCheckout画面が開かないことまでを確認しました。Checkout Sessionが重複作成されていないことをDBやStripe管理画面で確認した結果ではありません。
- Webhookによる自動反映は未実装のため、成功画面へ戻らない場合は利用者による再操作が必要です。
- 表示価格はテスト用であり、正式な販売価格ではありません。

## 採用技術

| 領域 | 技術 |
| --- | --- |
| フロントエンド | Next.js（App Router）、React、TypeScript |
| バックエンド | FastAPI、Python 3.12 |
| 認証 | Firebase Authentication |
| AI | OpenRouter / `openai/gpt-oss-120b` |
| データベース | PostgreSQL 16、SQLAlchemy、Alembic |
| 利用回数管理 | Redis 7 |
| 決済 | Stripe Checkout（テストモード・一回払い） |
| 開発環境 | Docker Compose |
| テスト | pytest、Vitest、Testing Library |

バージョンの正確な値は `frontend/package.json`、`frontend/package-lock.json`、`backend/requirements.txt` を参照してください。採用理由は [`docs/技術選定.md`](docs/技術選定.md) にまとめています。

## ディレクトリ構成

```text
frontend/
  app/                         Next.jsの画面とルーティング
  components/                  認証・相談・保存メモ・プラン等のUI
backend/
  app/
    core/                      設定、DB、共通エラー、ログ
    features/                  users、consultations、memos、usage、payments等
    integrations/             Firebase、OpenRouter等の外部接続
  migrations/                 Alembicマイグレーション
  tests/                       バックエンドテスト
docs/                          設計書、テスト設計、デモ手順
compose.yaml                   基本のDocker Compose設定
compose.firebase.yaml          Firebase Admin用JSON鍵の読み取り専用マウント
.env.example                   環境変数名と非秘密の開発用設定例
```

## 必要なもの

- Docker Desktop（Docker Compose v2を含むもの）
- Git
- Firebase Web SDKの公開設定
- リポジトリ外に保管したFirebase Admin SDKのサービスアカウントJSON
- OpenRouterのAPIキー
- 整理メモ暗号化鍵
- Stripe機能を確認する場合は、Stripeテストモードの設定

Node.jsとPythonはコンテナ内で実行します。秘密情報の取得・共有方法はREADMEには記載せず、チームで承認した安全な経路を使用してください。

## 初回セットアップ

### 1. `.env` を作る

リポジトリのルートで `.env.example` をコピーします。

```bash
cp .env.example .env
```

Windows PowerShellでは次を使用します。

```powershell
Copy-Item .env.example .env
```

`.env.example` の値だけでは、認証・AI・暗号化保存・決済を含む全機能は動作しません。空欄になっている外部サービス設定と秘密情報を、各自の `.env` にだけ設定してください。

- Firebase Web SDKの公開設定
- `FIREBASE_PROJECT_ID`
- `FIREBASE_CREDENTIALS_PATH`
- `OPENROUTER_API_KEY`
- `MEMO_ENCRYPTION_KEY`
- Stripeテストモードで必要な設定

`.env`、Firebase JSON、APIキー、トークン、暗号化鍵はGitへ追加しないでください。

> **Stripe設定について**
> アプリはStripe用の環境変数を参照しますが、2026年10月27日時点の `.env.example` と `compose.yaml` には、必要な設定項目がすべて整理されていません。結合確認済みの共有環境以外でStripeを動かす場合は、Issue #59・#62の設定と現在のComposeへの受け渡しを確認してください。この点は最終提出前のREADME再確認対象です。

### 2. Firebase JSONを準備する

Firebase Admin SDKのJSON鍵はリポジトリ外へ保存し、その絶対パスだけを `.env` の `FIREBASE_CREDENTIALS_PATH` に設定します。JSONの内容をREADME、Issue、PR、チャット、ログへ貼り付けないでください。

### 3. Docker Desktopを起動する

Docker Desktopを起動し、Engineが利用可能になるまで待ちます。

### 4. コンテナを起動する

Firebaseを含む全体確認では、2つのComposeファイルを使用します。

```bash
docker compose -f compose.yaml -f compose.firebase.yaml up --build -V
```

依存関係の更新後に古い `node_modules` を再利用しないよう、`-V` を付けています。ログを表示したまま、別のターミナルで後続コマンドを実行します。

Firebaseを使用しない基盤の起動だけであれば、次のコマンドも使用できます。

```bash
docker compose up --build -V
```

### 5. DBマイグレーションを適用する

コンテナ起動後、別のターミナルで実行します。

```bash
docker compose exec backend alembic upgrade head
```

マイグレーション未適用の新規DBでは、ユーザー・保存メモ・プラン・決済関連の処理とDBを使うテストが失敗します。

## 起動確認

| URL | 内容 |
| --- | --- |
| http://localhost:3000 | 開発環境の疎通確認画面 |
| http://localhost:3000/login | 新規登録・ログイン |
| http://localhost:3000/home | ログイン後のホーム |
| http://localhost:8000/health | FastAPIのヘルスチェック |
| http://localhost:8000/health/db | PostgreSQLのヘルスチェック |
| http://localhost:8000/health/redis | Redisのヘルスチェック |

認証が必要な画面へ未ログインで直接アクセスした場合は、ログイン画面へ戻ります。

## 縦断確認・デモ用の起動条件

相談中の一時状態はAPIプロセスのメモリにあるため、縦断確認・デモでは次を守ります。

1. `.env` の `BACKEND_RELOAD=false` を確認する
2. `backend/app/run.py` の設定どおり、APIを1ワーカーで起動する
3. 暗号化鍵を途中で変更しない
4. 同じアカウントで複数の相談を同時に開始しない
5. 相談を一時状態の有効時間内に完了する

本番Buildのフロントエンドを確認する場合は、開発サーバーとは分けて次を使用します。

```bash
docker compose run --rm --no-deps frontend npm run build
```

Build成功後の起動方法は、使用する環境とCompose設定を確認してから決めてください。開発用Composeは通常 `npm run dev` で起動します。

## テスト・Build

### CIと同等の通常テスト

```bash
docker compose exec backend pytest -v -p no:cacheprovider
docker compose run --rm --no-deps frontend npm test
docker compose run --rm --no-deps frontend npm run build
```

### 実DB・Redisを必須にするバックエンドテスト

```bash
docker compose exec \
  -e RUN_DB_TESTS=1 \
  -e REQUIRE_REDIS_TESTS=true \
  backend pytest -p no:cacheprovider -q -rs
```

### フロントエンド依存関係の脆弱性確認

```bash
docker compose run --rm --no-deps frontend npm audit --omit=dev
```

LintとフォーマッタのCI導入は提出後対応のため、現時点の `package.json` にはLintスクリプトがありません。

## 停止・リセット

コンテナを停止します。DBボリュームは保持されます。

```bash
docker compose -f compose.yaml -f compose.firebase.yaml down
```

DBを含むボリュームを削除して初期化する場合だけ、対象を確認したうえで `-v` を付けます。保存済みデータは失われます。

```bash
docker compose -f compose.yaml -f compose.firebase.yaml down -v
```

## 既知の制約・提出後対応

- 設定画面、ログアウト、退会のフロント導線は未実装です。
- 退会APIは実装済みですが、Firebase Authenticationの実削除、Stripe処理、手動復旧CLIを含む実運用確認は提出後対応です。
- Redisの不調が続く場合、退会後も利用回数のキーが残る可能性があります。
- 決済完了後に成功画面へ戻らなかった場合は直ちに有料状態へ反映されず、利用者による再操作が必要です。
- プラン設定値の読み込み口とAPI設計書の整理は提出後対応です。
- Redisの利用回数データは、現在のComposeでは永続化されません。
- AIの文章品質と安全案内の判定には、確率的な出力に由来する制約があります。他害や暴力を受けている状況はAI判定のみに依存し、実API確認では読み取りを見逃した例があります。
- 自傷・自殺に関するサーバー側のキーワード判定は、安全側に倒すため、否定文や一般的な説明、バーベキューの話に含まれる「練炭」などでも安全案内へ切り替わる場合があります。
- 429・5xxに対する自動再試行は、モックによる自動テストでのみ確認しています（実APIでは発生しなかったため未確認）。
- Next.jsのcritical脆弱性は `ff55b95` で解消済みです。Firebase依存を含む残存脆弱性は、最新の `npm audit --omit=dev` と関連Issueで継続確認します。
- デプロイ、監視、バックアップ、鍵ローテーションは未実装です。
- 実機のiPhone・iPad Safari確認は、Chromeのレスポンシブ表示確認とは区別します。

## Issue #62の縦断・異常系確認結果

2026年10月25日・28日に、Firebase実認証・実API・Stripeテストモードを使用して共同確認しました。結果記録のPR #121は2026年10月29日にマージされ、Issue #62はNGなしで完了しました。確認範囲と既知の制約の詳細は [`docs/test-results/mvp-scenarios.md`](docs/test-results/mvp-scenarios.md) を正とします。

- 保存しない相談で使用した目印文字列は、DB平文・BYTEA用16進数・Redis・frontend／backend／DB／Redisログのすべてで0件でした。
- 決済完了後、成功画面へ戻る前にタブを閉じた場合、再読み込み時点では無料プランのままでした。その後に購入操作を行うと、新しいCheckout画面を開かず有料プランへ反映されました。
- 相談途中にbackendを再起動すると、内部情報を含まない継続不可の案内とホーム導線が表示され、ホームから新しい相談を開始できました。
- 利用上限ちょうどの相談中にbackendを再起動した場合は、一時状態消失の案内が先に表示され、その後の新規相談で上限案内とプラン導線が表示されました。
- DB停止中の保存メモ一覧では、安全なエラー表示と再試行導線を確認しました。DB復旧後は元の一覧と詳細を表示でき、保存済みデータが保持されていました。
- 未ログイン状態で保護画面のURLへ直接アクセスすると、ログイン画面へ誘導されることを確認しました。期限切れ・失効トークンの401は自動テストで確認しています。
- DB停止中の詳細取得失敗と削除失敗は、実画面では個別に未確認です。
- AI失敗時のバックエンド側の再試行・状態不変・ログへの入力非出力は自動テストで確認済みですが、画面のエラー表示・入力保持・画面からの再送は未確認です。
- 設定・ログアウト・退会画面が未実装のため、ログアウトと退会の実画面確認は後続Issue #131へ引き継ぎます。

PR #121に記録されている最新の自動確認結果は、`develop` `ff55b95`でbackend 1,060件成功・36件skip、frontend 156件成功、frontend Build成功です。実DB・実Redisを必須にしたローカル確認では、backend 1,096件成功を記録しています。PR #121の最終HEAD `ef2b08c`でもCI 3件が成功し、`develop` `5d5eb3b`へマージ済みです。

## 開発時の注意

- GitHub運用は [`docs/github-rules.md`](docs/github-rules.md)、AIエージェント利用は [`AGENTS.md`](AGENTS.md) に従います。
- 共通設定ファイルを変更する場合は、関連Issueの担当者と事前に確認します。
- ログ・エラー・テスト記録に、相談内容、入力原文、AI出力、トークン、接続文字列、暗号文を残しません。
- `.env.example` には環境変数名と非秘密の例だけを記載し、実値は書きません。
- CORSは許可するフロントエンドのURLだけを設定し、`*` は使用しません。
- PostgreSQLとRedisのポートはホストへ公開せず、コンテナ間通信だけで使用します。

## うまく動かないとき

| 症状 | 確認すること |
| --- | --- |
| `.env` がないと表示される | `.env.example` をコピーしたか確認する |
| Firebase認証後に再ログインを求められる | Web SDKとAdmin SDKの接続先が一致しているか、JSONが読み取り専用で正しくマウントされているか確認する |
| 相談途中で状態が見つからない | `BACKEND_RELOAD=false`、1ワーカー、API再起動の有無、一時状態の有効時間を確認する |
| DBテーブルがないエラーになる | `docker compose exec backend alembic upgrade head` を実行する |
| 3000番・8000番ポートが使用中 | そのポートを使っている別のコンテナやアプリを停止する |
| 画面が更新されない | ブラウザ再読み込み後、必要なら `docker compose restart frontend` を実行する |
| パッケージ更新後も古い状態になる | `docker compose ... up --build -V` で匿名ボリュームを更新する |
| Stripeだけ動作しない | テストモード設定とComposeへの環境変数の受け渡しを確認する |

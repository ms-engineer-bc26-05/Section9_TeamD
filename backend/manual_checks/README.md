# Firebase最小権限の手動検証（#47・#93）

## 現在の実行計画案（#93・実行承認前）

**以下は承認依頼用の案。コードの準備完了を実接続の承認とは扱わない。**
PR #85は累計5回を使用済み。5回目の正常系はPASS（HTTP 5/10）、
その鍵はクラウド・ローカルとも削除済み。以前の承認を引き継がない。

### 対象・承認・期限

- 対象は `porori-auth-spike` の既存の専用サービスアカウントと架空テストユーザーのみ。
  共有DB・実データ・Stripe・フロントには接続しない。
- 実施者はもえ。実行承認者はじまさん・みほさんへ依頼中で、確定前。
  対象コミット・下記条件・料金条件を#93に記録し、明示的な実行承認後に開始する。
- 検証と結果記録は10月16日（金）20時頃までを目安とする。
  追加修正が必要なら影響・見込みを共有し、無断で追加実行しない。
- #53用認証情報とは分離する。発行・受け渡しは別途合意する。

### 実行方法と上限

- 使用モードは `--negative-only --approved`。正常系は再実行しない。
- 実接続プロセスは累計1回、権限不足・無効ユーザーの各1ケースを各1回。
  中断・失敗・コード修正後も回数をリセットしない。再起動は追加承認が必要。
- 各ケース最大10 HTTP送信試行・60秒、累計最大20試行・通信実行時間120秒。
  証明書取得・OAuth・SDK再試行を含む。最初のログインも権限不足ケースに算入する。
- ログインはスクリプト内で1回。APIキー・パスワードは非表示入力、
  トークンはメモリ内だけで2ケースに使用する。外部取得・ファイル保存・表示はしない。
- 手動入力・IAM反映待ちは60秒制限に含まれない。トークン期限の60秒前を停止期限とし、
  次ケース開始前に判定する。期限切れは再ログインせず停止する。
- 通信上限はrequests/urllib3の送信試行数で、DNS/TLSパケットやブラウザ内部通信数ではない。
  コンソールでの変更操作は下記7回以内とし、別に手動記録する。
  コンソール内部通信をスクリプトが制限するわけではない。

### 準備・操作順（承認後のみ）

事前に対象アカウントの現在のロールと専用ユーザーの有効状態を確認し、#93に記録する。
現時点ではクラウドの状態を再確認していない。ユーザーは有効であることを前提とする。
想定外のロール・対象・ユーザー状態なら計画を見直し、開始しない。

1. 専用の新規鍵を1個発行する。保存はリポジトリ外、#93専用の場所とする。
2. 専用サービスアカウントに#85のカスタムロールが残っていれば1回だけ外す。
   他の権限・継承権限がある場合は勝手に外さず停止する。
3. ロール反映を待ち、通信なしの自己テストを通した同じコード・依存環境で開始する。
   有効な専用ユーザーでログインし、ロールなしで `denied` を確認する。
4. PASS後、`firebaseauth.users.get`だけを含むカスタムロールを1回付与し、反映を待つ。
5. 専用テストユーザーを1回無効化する。非表示ログインで取得済みのトークンを使い、
   READYを入力して `disabled` を確認する。コンソール操作は人間が行う。
6. 成否にかかわらず後始末する。専用ユーザーを再度有効化（変更した場合に1回）、
   今回付与したロールを削除（1回）、今回の鍵をクラウドで削除（1回）する。
   サービスアカウント・カスタムロール定義自体は残す。他の鍵には触れない。
7. ローカルの今回のJSONを削除し、ファイルが存在しないことを確認する。
   コンソールの鍵一覧から今回の鍵が消えたことと併せて記録する。秘密値は記録しない。

コンソール変更は鍵発行1・初期ロール解除1・付与1・無効化1・再有効化1・
最終ロール解除1・鍵削除1の最大7回（ローカルファイル削除は別に1回）。
開始時にロールがなければ初期解除は不要。後始末の失敗も隠さず報告し、追加操作を相談する。

### 成功・停止・料金条件

- `denied`：実SDKのPermissionDeniedError、503 / AUTH_UNAVAILABLE、DB呼び出し0。
- `disabled`：実SDKのUserDisabledError、401 / UNAUTHORIZED、DB呼び出し0。
- 両ケースとも応答本文・ログの安全性検査がPASSすること。
  正常系、実DB登録、フロント結合の確認とは区別する。
- 想定外の応答・ログ、通信上限、期限切れ、認証情報不備、手動中断では停止。
  権限拡張・別ケース・手動再試行で回避しない。SDKの既定再試行も10回の枠内のみ。
- 費用は追加0円を条件とする案。実行直前に公式料金と対象プロジェクトのプラン・
  無料枠の適用を人間が確認し、根拠を#93へ記録する。まだ料金条件は確認済みではない。
  追加課金の可能性・料金不明・有料設定変更が必要なら開始しない。SMSは使わない。

結果記録には対象コミット、実行日時、プロセス累計、ケース別PASS/FAIL・試行数、
コンソール変更回数、停止理由、後始末、未確認事項を含める。
実行承認までは、以下の過去の実接続コマンドを流用しない。

### 準備段階の確認記録（2026-10-15）

- Python構文検査：成功。
- 標準ライブラリのみで関数を分離した通信なしの制御フロー検査：
  2ケース用10シナリオ、既存正常系専用8シナリオが成功。
  SDKを読み込んだ自己テストや実際の通信制限との結合テストの代わりにはしない。
- Docker起動後、既存イメージで`python -m manual_checks.firebase_connection --self-test`：PASS。
  `--network none`・読み取り専用・書き込み可能な`/tmp`で実行し、認証情報は渡していない。
  SDKを含む自己テストで、ケース順・停止条件・模擬応答・ログ検査と通信制限を確認した。
  実際のFirebase接続成功を意味するものではない。
- `git diff --check`：成功。
- Lint・Formatter：人間の承認後、一時環境へRuff 0.16.10を導入。
  PR #81の取得済み設定で`firebase_connection.py`の`ruff check`と
  `ruff format --check`が成功。リポジトリの依存設定は変更していない。
  期限変数の初期化・自己テストの変数束縛・import順を修正し、対象ファイルを整形した。
  修正後にSDK込みの`--self-test`も再実行しPASS。
- ビルド・Firebase実接続：未実施。実接続には具体計画の明示承認が別途必要。

## 過去の計画・手順（#85：終了済み、再実行不可）

この見出し以降は当時の記録であり、残り回数や許可を表すものではない。
通信なしの自己テスト手順だけは#93の準備にも利用する。

### PR #85の追加合意（当時）

以下の従来手順にある「最大4回」「3ケースの段階実行」は当初計画の記録。現在の累計上限は5回で、4回使用済み。残る5回目は **正常系だけ** に使う。回数はプロセス再起動やスクリプト修正でリセットしない。

- 使用するモードは `--allowed-only --approved`。`--guided`は使用しない。
- 有効な専用テストユーザーで非表示ログインを1回行い、`allowed`を1回確認して終了する。ログインを含む全HTTP送信試行を同じ最大10回・60秒の制限で囲む。入力待ちは含めない。
- 権限不足・無効ユーザーの実接続確認は後続Issueへ引き継ぐ方針。担当・期限・未確認事項は引き継ぎ先に記録する。
- 成功・失敗にかかわらず、この実行後の追加実接続は行わない。想定外の結果は停止してPRへ共有する。
- 対象プロジェクト、専用サービスアカウントの鍵、`firebaseauth.users.get`のみの権限と反映、専用ユーザーの有効状態、メール/パスワード認証、料金条件を実行前に確認する。権限を広げて回避しない。
- 成功条件は `check_revoked=True`の実SDK検証と、模擬DB登録を使う201応答・安全性検査。実DB登録やフロント結合の成功とは区別する。

通信なしのセルフテストで `PASS` を確認した後、上記の準備確認が済んだ場合だけ使用する。鍵・APIキー・パスワードを表示せず、画面録画・端末入力記録を停止する。

```bash
docker run --pull=never --rm -it --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,src=$PWD/backend/app,dst=/app/app,readonly" \
  --mount "type=bind,src=$PWD/backend/manual_checks,dst=/app/manual_checks,readonly" \
  --mount "type=bind,src=$HOME/.config/porori/issue-47/firebase-service-account.json,dst=/run/secrets/firebase.json,readonly" \
  --workdir /app --entrypoint /usr/bin/env team-d_project-review-backend:latest \
  -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  FIREBASE_PROJECT_ID=porori-auth-spike \
  GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/firebase.json \
  python -m manual_checks.firebase_connection --allowed-only --approved
```

`Type READY to start allowed verification:`を確認し、大文字の`READY`を入力する。続く非表示入力は対象プロジェクトのWeb APIキー、専用テストユーザーのパスワードの順。成功時は `allowed: PASS; HTTP attempts: N/10` と `PASS`を表示して終了する。トークンはメモリ内だけで受け渡す。

セルフテストには、正常系だけを1回実行すること、確認拒否時にログインしないこと、ログイン失敗・検証失敗・上限停止・中断で後続ケースや再試行へ進まないこと、秘密値を出力しないことの確認を含む。

## 実施範囲と開始条件

この手順は準備用。チームへの実施案が承認されるまで、サービスアカウント作成・権限付与・鍵発行・実接続を行わない。

- 対象は合意済みの開発用 `porori-auth-spike` のみ。
- Firebase IDトークンの検証は実接続、DBセッション・登録処理は常に模擬処理。
- 既存の登録Router・認証サービス・エラーハンドラを検証用FastAPIへ登録する。ポートは公開しない。
- 成功時の201は模擬ユーザーの応答。実DB保存・マイグレーション・フロント接続・通常API全体の結合確認ではない。
- 本番コード、main.py、Compose、依存パッケージは変更しない。通常のpytestでは実行しない。

実行前にIssueへ記録して承認を得る項目:

1. 専用サービスアカウント、`firebaseauth.users.get`のみのカスタムロール、鍵管理。
2. 専用の架空テストユーザーをコンソールで1人だけ作成する。下記の段階実行ではメール・パスワードによるログインを1回行い、トークンはメモリ内だけで引き継ぐ。作成済みなら追加作成しない。
3. アプリ操作は正常系・権限不足・ユーザー無効化の各1回、追加確認込み最大4回。1回のHTTP送信試行は最大10回、4回で最大40回。専用の架空テストユーザーの無効化操作も実施範囲に含める。
4. 料金条件を確認できなければ開始しない。有料設定・広い権限を追加して回避しない。

SDK 7.6.0の既存イメージ内ソースでは、HttpClientは接続・読み取りエラーで再試行1回、500/503で最大4回の再試行が既定。アプリ4回をHTTP4回とは扱わない。

### 検証スクリプトの停止上限

- トークンの非表示入力後、1プロセスの検証を最大60秒で停止する。入力待ちは含めない。
- 既存イメージのrequests/urllib3経由のHTTP送信試行を、証明書取得・OAuth認証情報取得・ユーザー照会・再試行を含めて最大10回まで許可する。11回目は送信前に停止する。接続失敗の試行も数える。
- urllib3の`HTTPConnectionPool._make_request`を検証プロセス内だけでラップする。HTTP/HTTPS共通経路を確認できない場合は開始しない。SDKの再試行設定や本番コードは変更しない。
- 停止には通常の`Exception`とは別の例外を使用し、SDKやAPI側のエラー変換で検証成功と誤認しないようにする。停止時は固定文言だけを表示する。
- LinuxコンテナのSIGALRMを使用する。依存ライブラリや通信方式を変更した場合は、この制限が適用されることを再確認する。
- 最大4プロセスという累計上限は手動記録で守る。プロセスの再起動で累計をリセットしない。上限到達後の追加実行は再相談する。
- この上限は検証スクリプトのHTTP試行数であり、DNS/TLSのパケット数やコンソール操作の内部通信は含めない。`--guided`のログイン通信は最初のケースの10回・60秒に含める。コンソールでの準備は専用ユーザー作成1回、無効化1回とし、既存ユーザーを変更しない。
- 費用見込みは、Sparkプラン・メール/パスワード認証・専用の架空ユーザー1人・無料枠内で追加0円。実行前にプランと適用条件を確認し、SMS・有料プラン変更は行わない。無料枠超過や料金条件が不明な場合は停止する。

**準備操作の計画・料金条件を含む実施記録をそろえるまでは実接続しない。** `--approved`は承認を代行する機能ではない。

## 通信なしの準備確認

リポジトリのルートで実行する。既存イメージを使用し、ビルド・ダウンロードしない。envファイルや鍵はマウントしない。

```bash
docker run --rm --network none --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,src=$PWD/backend/app,dst=/app/app,readonly" \
  --mount "type=bind,src=$PWD/backend/manual_checks,dst=/app/manual_checks,readonly" \
  --workdir /app --entrypoint /usr/bin/env team-d_project-review-backend:latest \
  -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  python -m manual_checks.firebase_connection --self-test
```

期待結果は `PASS`。正常・PermissionDenied・UserDisabledの判定、通信障害や不正トークンを成功と誤認しないこと、HTTP/HTTPSの試行上限、実際のurllib3再試行ループでの停止、時間上限と終了後の復元を通信なしで確認する。

### 証明書キャッシュの一時領域

- SDKの証明書取得に使われるCacheControlは、応答処理で一時ファイルを作成する。`--read-only`だけでは使用可能な一時領域がなく、`FileNotFoundError`になることを架空のHTTP応答で再現した。
- `--tmpfs /tmp:rw,noexec,nosuid,size=16m`で、コンテナ内のメモリ上に一時領域を用意する。鍵のマウントは読み取り専用のままで、ホストの保存先や本番設定は変更しない。
- 全実行モードの開始時に、架空の応答をCacheControlへ渡す事前チェックを行う。外部通信・実鍵・トークンは使用しない。失敗時は詳細を表示せず、非表示入力や実接続の前に停止する。
- 通信なしの確認では、一時領域なしで固定のSTOPと終了コード2、一時領域ありでセルフテストのPASSを確認する。
- この再現は実接続時の`OTHER_ERROR`と整合する原因候補であり、過去の実接続の例外を特定したものではない。修正後の実接続も未確認。過去の検証回数はリセットせず、追加実接続はPR上で合意した最新の計画に従う。

## 承認後の設定の渡し方

- 鍵はリポジトリ外へ置き、本人だけが読めるようにする。鍵の中身を表示・貼り付けしない。
- 鍵ファイル1個だけをコンテナの `/run/secrets/firebase.json` に読み取り専用でマウントする。
- `FIREBASE_PROJECT_ID=porori-auth-spike` と `GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/firebase.json` を渡す。後者は秘密鍵そのものではなく、コンテナ内のパス。
- 既存Composeにはこれらの指定がないため、今回の一時実行で明示する。`.env`は使用しない。
- トークンはスクリプトの非表示入力のみ。コマンド引数、環境変数、履歴、ファイル、チャットには書かない。画面録画・端末入力記録を停止し、入力後はクリップボードも消去する。

以下は承認後専用のテンプレート。`/ABSOLUTE/PATH/TO/KEY.json`を保管場所に置き換える。今は実行しない。

```bash
docker run --rm -it --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,src=$PWD/backend/app,dst=/app/app,readonly" \
  --mount "type=bind,src=$PWD/backend/manual_checks,dst=/app/manual_checks,readonly" \
  --mount "type=bind,src=/ABSOLUTE/PATH/TO/KEY.json,dst=/run/secrets/firebase.json,readonly" \
  --workdir /app --entrypoint /usr/bin/env team-d_project-review-backend:latest \
  -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  FIREBASE_PROJECT_ID=porori-auth-spike \
  GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/firebase.json \
  python -m manual_checks.firebase_connection --case denied --approved
```

## 実施順と期待結果

1. 専用アカウントに権限を付与していない状態で `--case denied` を1回実行。
   - 実SDKがPermissionDeniedErrorを返し、APIは503 / AUTH_UNAVAILABLE、DB処理0回であること。
   - 単なる503では成功としない。不正トークン・鍵設定ミス・通信障害は失敗。
2. 承認された最小権限のみ付与し、反映を待つ。同じ専用アカウントを使って新しいコンテナで `--case allowed` を1回実行。
   - `check_revoked=True`の検証成功後に模擬登録処理へ進み、201になること。
3. 正常系で使用した専用の架空テストユーザーを、管理コンソールで無効化する。共有デモ用や他メンバーのユーザーは変更しない。
   - 最小権限は維持し、無効化前に取得した有効期限内のIDトークンで `--case disabled` を1回実行する。
   - 実SDKがUserDisabledErrorを返し、APIは401 / UNAUTHORIZED、WWW-Authenticate: Bearer、DB処理0回であること。
   - 単なる401では成功としない。不正・期限切れのトークンや、ユーザー削除によるエラーは別ケースとして扱う。
   - トークンは非表示入力のみとし、ファイル・コマンド・チャットへ記録しない。
4. 想定外の結果では停止。IAM反映待ちを含め、連続再実行しない。追加実行は理由・累計回数を記録し、計画内で判断する。

プロセスはログをメモリ上で検査し、許可した固定文言以外・トレースバックを検出するとFAILにする。実UID・トークン・応答本文・例外詳細は出力しない。実接続前の初期化エラー等では、詳細を隠した固定FAILのみとなる。秘密情報を含む可能性のあるデバッグ出力を有効にして原因調査しない。

## トークンを表示しない段階実行

`--guided --approved`は、専用の架空ユーザー`issue47-auth-check@example.com`でログインし、上記3ケースを同一プロセス内で順番に実行する。プロジェクトのWeb APIキーと専用ユーザーのパスワードは非表示入力し、環境変数・引数・ファイルへ保存しない。鍵JSONの内容を入力するものではない。

- 既存の実行テンプレートの末尾を`--case denied --approved`から`--guided --approved`へ変更する。鍵のマウント方法や対象プロジェクトは変えない。
- 実行前に、このログイン方法と回数をIssueの検証記録へ追記する。対象プロジェクトのメール・パスワード認証が有効であることを確認する。APIキーの制限で拒否された場合は、制限を緩めず停止する。
- 最初の`READY`で専用アカウントにロールが未付与であることを確認する。非表示入力後、RESTの`signInWithPassword`を1回呼び、続けて権限不足ケースを実行する。ログインの自動再試行・リダイレクト・トークン更新はしない。
- `denied: PASS`の後で一時停止する。コンソールで専用アカウントに`firebaseauth.users.get`のみ付与し、反映を待ってから`READY`を入力する。自動的なIAM変更は行わない。
- `allowed: PASS`の後で再び停止する。専用テストユーザーだけをコンソールで無効化し、`READY`を入力する。ログインし直さず、無効化前の同じトークンで確認する。
- トークンは画面・ログ・ファイル・クリップボードへ出さない。終了時に参照を破棄するが、Pythonのメモリを暗号学的に消去する保証はない。録画・端末入力記録は停止する。
- 手動操作の待機中は60秒タイマーを停止する。ただしトークンの有効期限が近づいた場合は次のケースを開始せず停止する。期限切れを無効化成功とは扱わない。
- 3ケースはアプリ操作3回として記録する。同一プロセスでも各ケース最大10回・60秒、合計最大30HTTP試行。追加確認を含む全体上限4ケース・40HTTP試行は維持する。中断したケースも1回として数え、再起動しても累計をリセットしない。ログイン失敗も最初のケース1回として記録する。
- FAIL・STOPならそこで終了し、設定や回数を確認するまで再実行しない。3ケース全体を無条件にやり直すと最大4回を超えるため、自動・手動の一括再実行はしない。
- 非表示ログイン処理は通信ログを抑止する。実際のAPIエラー応答・ログの安全性は、続く既存の`probe`で検査する。

## 終了と記録

- 段階実行で例外が起きた場合も、停止段階（`SIGN_IN`/`TOKEN_PROBE`/`GUARD`）とHTTP試行数を表示する。ガード開始前なら試行数は`UNKNOWN`とする。ログインの固定分類は`SIGN_IN_HTTP_REJECTED`（非200応答）、`SIGN_IN_TRANSPORT_FAILED`（通信失敗）、`SIGN_IN_RESPONSE_INVALID`（応答形式不正）。HTTP拒否だけでパスワード誤りとは断定しない。その他は`UNEXPECTED_ERROR`として本文・例外詳細を隠す。上限停止・中断でも自動再試行しない。
- ケースのFAIL時には、固定カテゴリの`DIAGNOSTIC`でSDK結果・HTTP分類・DB呼び出し有無・ケース条件・ログ・本文検査の成否を表示する。例外メッセージ、例外名の動的出力、レスポンス本文、トークン、UIDは表示しない。`NOT_REACHED`や`OTHER_ERROR`だけでは原因を断定しない。
- 診断表示を追加しても検証上限は変わらない。過去のFAILも累計に含め、再実行前に残り回数と必要ケースを確認する。
- SDKのGoogle認証エラーは`GOOGLE_AUTH_REFRESH_FAILED`（認証情報更新）、`GOOGLE_AUTH_CREDENTIALS_ERROR`（認証情報の検出・検証）、`GOOGLE_AUTH_TRANSPORT_FAILED`（通信）、`GOOGLE_AUTH_OTHER_ERROR`に分類する。requestsの通信エラーは`HTTP_TRANSPORT_FAILED`とする。例外型に基づく分類であり、鍵の失効・設定ミス等の具体的原因を断定するものではない。これらは期待する権限不足とは別のため、503でもケースはFAILのままとする。

- 検証終了後、もえがクラウド側で今回の鍵を削除し、ローカルのJSONも削除する。Gitの削除ではなく認証情報の無効化が必要。
- テストユーザー・専用アカウント・カスタムロールの後始末は承認された範囲で行う。既存アカウントや他メンバーのデータを削除しない。
- 継続開発用の認証情報は別途管理方法を合意する。
- PRにはコミット、SDK版、ケース、回数、PASS/FAIL、未確認事項、鍵の削除状況だけを記録する。鍵・トークン・実UIDは載せない。
- 未確認: 実DB登録、フロント結合、実環境でのユーザー無効化（今回の検証予定）、トークン失効操作による検証、継続開発用の鍵管理。

## 参照

- [Firebase Admin SDK設定](https://firebase.google.com/docs/admin/setup)
- [Python verify_id_token](https://firebase.google.com/docs/reference/admin/python/firebase_admin.auth#firebase_admin.auth.verify_id_token)
- [IDトークン検証](https://firebase.google.com/docs/auth/admin/verify-id-tokens)
- [Firebase料金](https://firebase.google.com/pricing)
- [Firebase Authenticationの制限](https://firebase.google.com/docs/auth/limits)
- [Firebase Auth REST API（メール・パスワードのログイン）](https://firebase.google.com/docs/reference/rest/auth#section-sign-in-email-password)

# Firebase最小権限の手動検証（#47）

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
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,src=$PWD/backend/app,dst=/app/app,readonly" \
  --mount "type=bind,src=$PWD/backend/manual_checks,dst=/app/manual_checks,readonly" \
  --workdir /app --entrypoint /usr/bin/env team-d_project-review-backend:latest \
  -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  python -m manual_checks.firebase_connection --self-test
```

期待結果は `PASS`。正常・PermissionDenied・UserDisabledの判定、通信障害や不正トークンを成功と誤認しないこと、HTTP/HTTPSの試行上限、実際のurllib3再試行ループでの停止、時間上限と終了後の復元を通信なしで確認する。

## 承認後の設定の渡し方

- 鍵はリポジトリ外へ置き、本人だけが読めるようにする。鍵の中身を表示・貼り付けしない。
- 鍵ファイル1個だけをコンテナの `/run/secrets/firebase.json` に読み取り専用でマウントする。
- `FIREBASE_PROJECT_ID=porori-auth-spike` と `GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/firebase.json` を渡す。後者は秘密鍵そのものではなく、コンテナ内のパス。
- 既存Composeにはこれらの指定がないため、今回の一時実行で明示する。`.env`は使用しない。
- トークンはスクリプトの非表示入力のみ。コマンド引数、環境変数、履歴、ファイル、チャットには書かない。画面録画・端末入力記録を停止し、入力後はクリップボードも消去する。

以下は承認後専用のテンプレート。`/ABSOLUTE/PATH/TO/KEY.json`を保管場所に置き換える。今は実行しない。

```bash
docker run --rm -it --read-only --cap-drop ALL --security-opt no-new-privileges \
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

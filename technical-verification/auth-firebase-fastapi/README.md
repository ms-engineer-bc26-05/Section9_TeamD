# Firebase Authentication・FastAPI 認証／認可の技術検証

## 対応Issue

- Issue #5
- 主担当：もえ
- 確認担当：みほ・じま
- 状態：PR #21のレビュー指摘に対応中

## 目的

Firebase Authenticationで発行したIDトークンをFastAPIで検証し、
ログインした本人のデータだけにアクセスを許可できるか確認する。

- 認証：誰がアクセスしているかを確認する。
- 認可：そのユーザーが対象のデータを操作してよいか判断する。

## 前提

- Issue #2の暫定案を前提に実施する。
- 検証用FirebaseプロジェクトはSparkプランで作成済み。
- メール／パスワード認証を有効化済み。
- 架空の検証用ユーザーを2人作成済み。
- Python 3.12のDocker環境を使用する。
- 実在の相談内容は使用しない。

## 検証すること

- 以下の状態欄は、実際のFirebaseを利用した検証の実施状況を示す。
- ローカル模擬テストの結果は「検証結果」に記載する。

| 項目 | 期待する結果 | 状態 |
| --- | --- | --- |
| 有効なIDトークン | 認証に成功する | 実接続確認済み：200 |
| 無効なIDトークン | アクセスを拒否する | 署名改変で確認済み：401 |
| 期限切れのIDトークン | アクセスを拒否する | 実トークンの期限切れを確認済み：401 |
| トークン未指定 | アクセスを拒否する | 確認済み：401 |
| 本人のデータへのアクセス | アクセスを許可する | 実接続確認済み：200 |
| 他人のデータへのアクセス | アクセスを拒否する | 実接続確認済み：404 |
| ログ・エラーレスポンス | トークン・秘密鍵・本文が含まれない | 検査対象レスポンスとPythonのINFO以上の収集ログで混入なし。対象外は検証結果に記載 |

- ローカルの模擬テストと、実際のFirebaseを利用した検証は、区別して結果を記録する。

## 実施しないこと

- パスワード認証の自作
- 本番Firebaseプロジェクトの完成設定
- 全画面へのログイン組み込み
- メモCRUDの本実装
- 本番環境・共有DBの操作

## 費用・外部リクエストの管理

### 実接続の検証計画

- 対象：検証用Firebaseプロジェクトのメール／パスワード認証
- 使用データ：架空ユーザーA・B、架空メモ1件
- 費用見込み：Sparkプランの無料範囲内で0円
- 外部への検証リクエスト：合計最大10回
  - 当初の内訳：ログイン2回、公開証明書取得など最大8回
  - 再試行を含む実績：累計9回、残り1回（詳細は検証結果に記載）
  - 再試行も合計に含める。自動再試行は行わない。
- ローカルAPIへのアクセスと、SDKが行う外部通信は区別して記録する。
- 通信回数を確認できる実行方法を用意してから開始する。

成功条件：
- 有効なIDトークンで認証に成功する。
- 無効・期限切れ・未指定トークンを拒否する。
- 本人の架空メモは取得でき、他人のメモは取得できない。
- トークン・パスワード・秘密鍵をログや結果へ出力しない。
- 模擬テストと実際のFirebaseを使った結果を分けて記録する。

停止条件：
- 有料設定や請求先の登録が必要になった場合
- 想定外のエラー、Firebase側の権限不足・利用制限が発生した場合
  - 無効・期限切れ・未指定トークンへの401や、
    他人のメモへの404は期待する結果のため、停止対象には含めない。
- 外部通信回数が把握できない場合
- 合計10回に達した場合

- 外部サービスへの検証リクエストは最大10回とする。
- 無料範囲・料金条件を公式資料で確認してから実行する。
- 料金確認日：2026年9月23日
- 利用プラン：Spark
- 利用機能：メール／パスワード認証
- 利用者：架空の検証用ユーザー2人
- 実行環境：手元のDocker
- Firebase利用料の見込み：0円
- 電話番号認証・SMS送信・有料サービスは利用しない。
- Blazeプランへの変更や請求先の登録は行わない。
- 公式資料：
  - https://firebase.google.com/pricing
  - https://firebase.google.com/docs/auth/limits
- 有料設定が必要な場合、費用が判断できない場合、
  または上限を超える場合は停止し、チームに確認する。

### 追加検証：期限切れとログ

- 開始前の外部通信累計：7回。追加は最大3回。
- 内訳：ユーザーAのログイン1回、公開証明書取得は最大2回。
- 有効な実トークンを検証後、メモリ上に保持して期限切れまで待つ。
- トークンの書き換え・自動更新・ファイル保存は行わない。
- 期限切れ後、SDKのExpiredIdTokenErrorとAPIの401を確認する。
- PythonのINFO以上のログをメモリ上で収集し、
  入力した秘密情報・トークン・架空メモ本文の混入を確認する。
- ログ内容そのものは表示・保存しない。
- 本番環境やUvicornのログ全体を確認するものではない。

## 秘密情報の扱い

- 秘密鍵・パスワード・認証トークンをGitへ登録しない。
- 認証トークン・秘密鍵・相談本文をログに出力しない。
- 秘密情報をIssue・PR・チャットへ貼り付けない。
- AIエージェントは.env.example以外のenvファイルを読み書きしない。

## 実行手順

### 1. 準備

- Dockerを起動する。
- 検証用Firebaseプロジェクトでメール／パスワード認証を有効にする。
- 架空の検証ユーザーA・Bを用意する。
- サービスアカウントの秘密鍵JSONをリポジトリ外へ保管する。
- 以下の手順では秘密鍵を
  `$HOME/porori-local-secrets/firebase-admin.json` に置く。
- コマンドはリポジトリのルートで実行する。
- 入力例はmacOSのzshを前提とする。
- 設定値・秘密鍵・パスワード・トークンをGitへ登録しない。

### 2. ビルドとローカル模擬テスト

```bash
docker build -t porori-auth-spike ./technical-verification/auth-firebase-fastapi
```

```bash
docker run --rm --network none porori-auth-spike python -m pytest -q -p no:cacheprovider
```

模擬テストではFirebaseへの通信を行わない。

### 3. 設定値の入力とAPI起動

同じターミナルで順に実行する。
各入力待ちで値を貼り付け、Enterで確定する。

```bash
read -rs "FIREBASE_PROJECT_ID?プロジェクトID: "
```

```bash
read -rs "VERIFICATION_OWNER_UID?ユーザーAのUID: "
```

```bash
export FIREBASE_PROJECT_ID VERIFICATION_OWNER_UID
```

```bash
docker run --rm --name porori-auth-spike \
  -p 127.0.0.1:8001:8000 \
  -e FIREBASE_PROJECT_ID \
  -e VERIFICATION_OWNER_UID \
  -e GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/firebase-admin.json \
  --mount "type=bind,source=$HOME/porori-local-secrets/firebase-admin.json,target=/run/secrets/firebase-admin.json,readonly" \
  porori-auth-spike
```

秘密鍵は読み取り専用で渡し、Dockerイメージには含めない。
このターミナルはAPIを起動したままにする。

### 4. 起動確認

別のターミナルを開き、リポジトリのルートで実行する。

```bash
curl -i http://127.0.0.1:8001/health
```

期待結果：200、`{"status":"ok"}`

```bash
curl -i http://127.0.0.1:8001/private
```

期待結果：401、`{"detail":"Authentication required"}`

これらのリクエストではFirebaseへの通信は発生しない。

### 5. 実接続検証の準備

以下は外部通信を伴う。
実行前に検証記録の累計回数と残り枠を確認する。

- 上限は失敗・再試行を含めて合計10回。
- スクリプトのカウンターは実行ごとにリセットされる。
- 累計は自動管理されないため、実行後に必ず記録する。
- 残り枠が不明・不足する場合は実行せず、チームに確認する。
- STOPが出た場合は、そのまま再実行しない。

手順4のターミナルでWeb APIキーを入力する。

```bash
read -rs "FIREBASE_WEB_API_KEY?Web APIキー: "
```

```bash
export FIREBASE_WEB_API_KEY
```

検証スクリプトを起動中のコンテナへコピーする。

```bash
docker cp ./technical-verification/auth-firebase-fastapi/verify_live.py porori-auth-spike:/app/verify_live.py
```

```bash
docker cp ./technical-verification/auth-firebase-fastapi/verify_expiry.py porori-auth-spike:/app/verify_expiry.py
```

### 6. 認証・認可の実接続検証

`verify_live.py`のMAX_REQUESTSを残り枠以内に設定し、
変更した場合はコンテナへ再コピーしてから実行する。

```bash
docker exec -it -e FIREBASE_WEB_API_KEY porori-auth-spike python /app/verify_live.py
```

入力するのは、検証ユーザーA・Bのメールアドレスとパスワード。
Firebaseコンソールへログインする管理者の情報ではない。

実際のFirebaseでログインし、Admin SDKでトークンを検証する。
FastAPIへのアクセスにはTestClientを使用する。
結果と通信回数だけを記録し、認証情報は記録しない。

### 7. 実トークンの期限切れ・ログ確認

今回の追加検証は、先行検証7回・残り3回を前提とする。
`verify_expiry.py`はこの前提をコード内に持つため、
別の検証で再利用する場合は回数設定を見直す。

```bash
caffeinate -i docker exec -it -e FIREBASE_WEB_API_KEY porori-auth-spike python /app/verify_expiry.py
```

検証ユーザーAの情報を入力する。
トークンをメモリ上に保持し、実際の期限切れまで約1時間待機する。
Macのふたを開け、Dockerとターミナルを起動したままにする。

確認範囲：
- 期限内の認証成功
- SDKによる実トークンの期限切れ検出
- 期限切れトークンへのAPIの401応答
- 収集したPythonのINFO以上のログと検査対象レスポンスへの
  入力した認証情報・IDトークン・架空メモ本文などの混入

ログはメモリ上で検査し、内容を表示・ファイル保存しない。
本番環境やUvicornのログ全体を検証するものではない。

### 8. 検証終了後

期限切れ検証が終了し、結果と通信回数を記録してから行う。

- APIを動かしているターミナルでControl+Cを押して停止する。
- コンテナは--rm指定により停止後に削除される。
- ホスト側の秘密鍵ファイルは削除されない。
- 各ターミナルで、使用した環境変数を解除する。

```bash
unset FIREBASE_PROJECT_ID VERIFICATION_OWNER_UID FIREBASE_WEB_API_KEY
```

### Windows（PowerShell）での読み替え

以下はWindows向けの補足手順です。Windows実機での動作確認は未実施です。
Docker Desktopを起動し、リポジトリのルートで操作します。

#### 環境変数の入力

macOSの `read -rs` と `export` の代わりに、次を使用します。
PowerShell 5.1・7系で入力内容を画面に表示しない方法です。

```powershell
function Read-HiddenValue {
    param([string]$Prompt)

    $secureValue = Read-Host $Prompt -AsSecureString
    $pointer = [IntPtr]::Zero
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        if ($pointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
        $secureValue.Dispose()
    }
}

$env:FIREBASE_PROJECT_ID = Read-HiddenValue "プロジェクトID"
$env:VERIFICATION_OWNER_UID = Read-HiddenValue "ユーザーAのUID"
$env:FIREBASE_WEB_API_KEY = Read-HiddenValue "Web APIキー"
```

環境変数に渡した値はプロセス内では平文になります。
値の表示や、画面・ログへの出力は行いません。
`Read-Host -MaskInput` はPowerShell 7.1以降でのみ使用できます。

#### コマンドの違い

- 行末の `\` はPowerShellでは使用しません。
  コマンドを1行にまとめるか、バッククォート（`）で改行します。
  バッククォートの後ろに空白を入れないでください。
- `curl -i` は `curl.exe -i` に読み替えます。
- `docker build`・`docker cp`・`docker exec` は、同じ引数を1行にまとめて実行できます。
- ホスト側の秘密鍵ファイルのパスは、Windowsでの実際の配置先へ読み替えます。
  コンテナ内の `/run/secrets/firebase-admin.json` は変更しません。
- macOSの `chmod` は使用せず、Windowsのファイルアクセス権で保護します。
- `caffeinate -i` は使用できません。
  期限切れ検証ではその部分を外し、Windowsの電源設定で検証中のスリープを防止します。
  検証後は電源設定を元に戻してください。

実接続スクリプトは外部通信を伴います。
現在の累計は9回／上限10回のため、一式の再実行はせず、
追加検証が必要な場合はチームと上限を確認してください。

#### 終了後の環境変数の削除

```powershell
Remove-Item Env:FIREBASE_PROJECT_ID -ErrorAction SilentlyContinue
Remove-Item Env:VERIFICATION_OWNER_UID -ErrorAction SilentlyContinue
Remove-Item Env:FIREBASE_WEB_API_KEY -ErrorAction SilentlyContinue
Remove-Item Function:Read-HiddenValue -ErrorAction SilentlyContinue
```

## 検証結果

### ローカル模擬テスト（2026年9月23日）

実行コマンド：

docker run --rm --network none porori-auth-spike python -m pytest -q -p no:cacheprovider

結果：16 passed, 1 warning

- Firebaseの初期化・トークン検証処理をモックに置き換えて実施した。
- ネットワークを遮断し、外部通信なしで実施した。
- 認証成功、不正・期限切れ・未指定トークンの拒否を確認した。
- 本人の架空メモの取得と、他人のメモへのアクセス拒否を確認した。
- 設定・検証処理の異常時にアクセスを許可しないことを確認した。
- テスト対象のレスポンスと取得したログに、
  ダミートークンや内部エラーの詳細が出ないことを確認した。
- ライブラリ内部の非推奨APIに関する警告が1件あった。

模擬テスト実施時点の未確認事項（実接続結果は後述）：
- 実際のFirebaseが発行したIDトークンの検証
- 実接続時のログ・レスポンス

### 起動確認（2026年9月23日・実接続検証前）

- Dockerイメージのビルド：成功
- コンテナの起動：成功
- GET /health：{"status":"ok"} が返ることを確認
- Firebaseへの認証リクエスト：まだ実施していない
- 認証・認可の実接続テスト：未実施

### 起動したAPIでの未指定トークン確認

- GET /private にAuthorizationヘッダーなしでアクセスした。
- 結果：401 Unauthorized
- WWW-Authenticate: Bearer が返った。
- レスポンス：{"detail":"Authentication required"}
- この確認によるFirebaseへの外部通信：0回

### Firebase実接続検証（2026年9月23日）

- Firebaseで作成した架空ユーザーA・Bでログインした。
- 実際に発行されたIDトークンをFirebase Admin SDKで検証した。
- FastAPIへのリクエストはTestClientから送信した。
- Firebaseの初期化・トークン検証はモックに置き換えていない。

| 確認内容 | 結果 |
| --- | --- |
| トークン未指定 | 401：期待どおり |
| 有効なIDトークン | 200：期待どおり |
| 本人の架空メモ | 200：期待どおり |
| 他人の架空メモ | 404：期待どおり |
| 署名を改変したIDトークン | 401：期待どおり |

今回の外部通信試行数：3回
内訳：ログイン2回、公開証明書取得1回

外部通信の累計：7回／上限10回

- 初回・再試行の失敗分：各2回、計4回
- 修正後の成功分：3回
- 残りの検証枠：3回
- 外部通信を遮断した診断は含めない。

先行する検証では通信カウンターの引数定義に不備があり、
有効なトークンの確認で503となった。
引数定義を修正し、外部通信なしの診断後に再検証した。

追加検証前の未確認事項（確認結果は次節に記載）：
- 実際に期限が切れたIDトークンの拒否
  （期限切れ例外を使った模擬テストは成功済み）
- 運用時のログへの秘密情報混入
  （今回の実接続スクリプトではライブラリログを抑止）

### 実トークンの期限切れ・ログ確認

- ユーザーAでログインし、期限内の認証成功（200）を確認した。
- 本人の架空メモの取得成功（200）を確認した。
- 同じIDトークンをメモリ上に保持し、実際の期限切れまで待機した。
- Firebase Admin SDKがExpiredIdTokenErrorを返すことを確認した。
- 期限切れトークンに対し、FastAPIが401を返すことを確認した。
- 検査対象のレスポンスと、収集したPythonのINFO以上のログに、
  検査対象の認証情報・IDトークン・架空メモ本文等の混入はなかった。
- 本番環境・Uvicornのログ全体・DEBUGログは、この確認の対象外。

追加検証の外部通信：2回
内訳：ログイン1回、公開証明書取得1回

最終累計：9回／上限10回
- 先行する検証：7回
- 期限切れ・ログの追加検証：2回
- 残り枠：1回

## UIDとアプリ内ユーザーの対応方針

### 検証で確認したこと

- Firebase Admin SDKが検証したIDトークンからUIDを取得した。
- 検証用メモの所有者UIDと、認証済みユーザーのUIDを比較した。
- 一致する場合は取得を許可し、不一致の場合は404を返した。
- 存在しないメモも404とし、他人のメモの存在を知らせない。
- 今回は環境変数とメモリ上の架空データで検証しており、
  DBとの連携は未実装である。

### 本実装に向けた設計案（DB設計で確認）

- usersテーブルに、内部ユーザーIDとfirebase_uidを持たせる。
- firebase_uidにはNOT NULL・UNIQUE制約を付ける。
- 整理メモのuser_idを、usersの内部ユーザーIDへ紐づける。
- バックエンドは、検証済みトークンのUIDから内部ユーザーを特定する。
- メールアドレスはユーザーの識別キーとして使用しない。
- クライアントが送ったUIDやuser_idを、本人確認の根拠にしない。
- メモの取得・削除では、メモIDと認証済みの内部ユーザーIDを
  条件にして、本人所有のデータだけを対象とする。
- 初回ログイン時の内部ユーザー作成と退会時の処理は、
  API・DB設計で確定する。

### 本実装で行う認可テスト案（未実施）

以下は後続のAPI・DB実装で行うテスト案であり、
今回の検証で実施済みの結果とは区別する。
ユーザーA・Bと、それぞれが所有する架空メモを用意する。

| 対象 | 操作 | 期待する結果 |
| --- | --- | --- |
| 取得 | AがBのメモを取得する | 404となり、本文や所有者情報を返さない |
| 削除 | AがBのメモを削除する | 404となり、Bのメモは削除されない |
| 削除 | AがAのメモを削除する | 削除でき、以後の取得は404となる |
| 一覧 | Aがメモ一覧を取得する | Bのメモが含まれず、総件数にも含まれない |
| 所有者IDの偽装 | Aが保存リクエストにBのuser_idやUIDを指定する | 不正な項目を拒否するか無視し、Bの所有物として保存されない |
| 所有者の決定 | Aが正規の保存リクエストを送る | 検証済みトークンのUIDから特定した内部ユーザーAが所有者になる |
| 未認証 | トークンなし・不正・期限切れで一覧・保存・削除を試す | アクセスを拒否し、データを変更しない |
| 退会中 | deletingのユーザーが保護対象APIへアクセスする | 通常の閲覧・保存・決済操作を拒否する |
| 退会後 | 退会前に発行されたトークンでアクセスする | データへのアクセスを拒否し、削除済みユーザーを自動再作成しない |
| 失効・無効化 | 失効済みトークンや無効化済みユーザーでアクセスする | 本実装で定める反映タイミングに従って拒否する |

- 拒否時は、HTTP応答だけでなくDBに意図しない変更がないことも確認する。
- 所有者の判定には、クライアントが申告したIDではなく、
  検証済みトークンのUIDに対応する内部ユーザーIDを使用する。
- 退会後・失効・ユーザー無効化の拒否は、
  現在のcheck_revoked=Falseだけで保証されるものではない。
  アプリ内ユーザーの状態確認とFirebase側の確認方針を定めて検証する。
- 保存済みメモの再編集はMVP対象外のため、更新APIのテストは対象に含めない。

## 代替案との比較

調査日：2026年9月23日

Firebaseは実接続検証を実施した。
fastapi-usersは公式資料による比較であり、動作検証は未実施。

| 観点 | Firebase Authentication＋Admin SDK | fastapi-users |
| --- | --- | --- |
| 役割 | 外部の認証サービスを利用し、FastAPIでIDトークンを検証する | FastAPIへ認証・ユーザー管理機能を組み込むライブラリ |
| 実装負担 | Firebaseの設定、フロントのログイン処理、バックエンドのトークン検証が必要 | ユーザーDB、認証方式、メール送信との連携などの設定が必要 |
| パスワード管理 | Firebaseへ委ね、アプリDBにパスワードを保存しない | ライブラリのハッシュ処理を利用し、自分たちのDBで認証情報を管理する |
| 安全性の責任 | トークン検証、設定・秘密鍵の管理、本人所有データの認可はチームで実装する | ライブラリの更新に加え、認証DB・署名鍵・認証設定・認可をチームで管理する |
| チームの習熟度 | Issue #5にチーム内の利用経験が記載されている | チーム内の利用経験は未確認 |
| 外部依存 | Firebaseの利用条件・制限・サービス稼働に依存する | 自分たちの認証基盤の運用とライブラリの保守に依存する |
| 保守状況 | Googleの公式サービス・Admin SDKを利用する | メンテナンスモード。セキュリティ更新と依存関係の保守を継続、新機能追加は行わない |
| 今回の確認 | 実トークンの検証と本人・他人のデータへのアクセス制御を確認済み | 資料調査のみ |

どちらの方式でも、ログインできることと、
本人のデータだけを操作できることは別に確認する必要がある。

参考資料：
- [Firebase Authentication](https://firebase.google.com/docs/auth)
- [IDトークンの検証](https://firebase.google.com/docs/auth/admin/verify-id-tokens)
- [FastAPI Users](https://fastapi-users.github.io/fastapi-users/latest/)

## 推奨方式・残る設定作業

### 暫定推奨

Firebase Authentication＋Firebase Admin SDKを推奨候補とする。

理由：
- チームに利用経験がある。
- アプリ側でパスワードの保管・照合を実装せずに済む。
- 今回の検証で、実際のIDトークンの検証と、
  本人所有データへのアクセス制御が成立することを確認できた。

実装負担の比較は、今回の検証と公式資料に基づく判断であり、
両方式の実装工数を実測したものではない。
正式採用は残る確認とチームレビューを経て決定する。

### Issue #5で残る確認

- 提出対象ファイルの差分・秘密情報混入の最終確認
- 記載した実行手順と検証範囲のレビュー
- 確認担当のみほさん・じまさん両名のApprove

外部通信は累計9回／上限10回。
既存の実接続スクリプトを一式再実行する枠は不足しているため、
レビュー時に追加実行が必要な場合は、事前にチームへ確認する。

### 本実装で決める事項

- フロントエンドのログイン・ログアウトとトークン更新
- Firebase UIDと内部ユーザーの対応、初回登録処理
- 退会時のFirebaseユーザーとアプリDBの削除処理
- メールアドレス確認・パスワード再設定の扱い
- チームメンバーの権限と開発環境の管理
- 秘密鍵の保管・更新・失効方法
- 無効化したユーザーや失効済みトークンへの対応方針

今回のコードはcheck_revoked=Falseとしているため、
トークンの失効・ユーザー無効化の確認は実施していない。
本実装では必要な反映タイミングと追加通信を考慮して方針を決める。

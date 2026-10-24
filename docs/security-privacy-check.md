# ぽろり。セキュリティ・プライバシー確認の記録（Q-03）

- 作成日：2026年10月23日
- 最終修正日：2026年10月24日（PR #120のレビューを反映）
- 対応Issue：#63「認証認可・暗号化・非保存・ログを確認する」
- 主担当：じま
- 確認担当：もえ
- 確認観点の一覧と進め方：#63のコメント（10/12）。もえさんの補足（10/12）を反映

## 1. 目的・記録のルール

テスト設計書の非保存確認（6章）とセキュリティの観点を、MVPの中心フローで確認した結果を記録する。

- 結果は「OK／NG／制約／未確認」で書く
  - **OK**：確認して問題がなかった
  - **NG**：問題があった（不具合Issueの番号を書く）
  - **制約**：確認したうえで、MVPでは対応しないと決めたもの
  - **未確認**：時間や依存関係の都合で確認できなかったもの。理由・引き継ぎ先・次の確認時期を書く
- 値（鍵・トークン・入力した文・IDなど）は記録しない。検索した範囲・方法と、件数だけを書く（テスト設計書6.6）
- 使ったのは架空の検証用ユーザーと架空の文だけ。実在の相談内容は使っていない

## 2. 確認の方法と条件

| 方法 | 内容 | 実施日 | 対象のコミット |
| --- | --- | --- | --- |
| A. 自動テストの確認 | テスト設計書のテストIDに当たるテストがあるかを、テストのコードで確かめる | 10/15、10/23 | developの`146c2db`（10/15）、`edcf33b`（10/23） |
| B. コードの確認 | 所有者確認・ログ・SQLの組み立て方などを、コードを読んで確かめる | 10/12、10/15、10/23 | 同上 |
| C. 結合後の手動確認 | 画面で中心フローを通したあと、DB・Redis・ログを検索する | 10/23 | developの`edcf33b` |

### 方法Cの条件（10/23）

- 環境：ローカルのDocker Compose（`compose.yaml`＋`compose.firebase.yaml`）。DB・Redis・ログを空にしてから開始し、`LOG_LEVEL=DEBUG`で起動した。共有環境・本番環境は使っていない
- 認証：実際のFirebase Authentication。バックエンドは専用のサービスアカウントで、権限は`firebaseauth.users.get`だけ
- AI：実際のOpenRouter。相談は2回だけ行った
- ユーザー：架空の検証用ユーザーA・B（`example.com`のメールアドレス）
- 操作：Aで相談を2件行い、整理メモを2件保存した（1件は出来事の確認で訂正を1回、もう1件はXSS用の文字列を入力）。Bは登録だけ
- 入力した文には、項目ごとに目印文字列（`PORORI_TEST_MARKER_Q03_…`）を入れた（テスト設計書6.2）

### 方法Cで検索したもの

| 対象 | 方法 |
| --- | --- |
| DB | `pg_dump --data-only`の出力を、目印文字列、目印の16進数、`<script`で検索。`approved_memos`の列の型と件数 |
| Redis | `redis-cli --scan`のキー名、`TYPE`・`HKEYS`、`HGETALL`の出力を目印文字列で検索 |
| ログ | `docker compose logs`（backend・db・frontend・redis）を、目印文字列、`eyJ`、`Bearer `、暗号化の鍵、OpenRouterのキー、Firebaseの鍵のID、`BEGIN PRIVATE KEY`で検索。鍵の値は変数に入れて検索に使うだけで、表示していない |

## 3. 結果

| No | 観点 | テスト設計書のID | 結果 | 方法 |
| --- | --- | --- | --- | --- |
| 1 | 認証（トークンなし・不正・期限切れ・認証基盤の障害時に許可しない） | AU-05〜AU-11、NP-13 | OK | A・B・C |
| 2 | 他人のデータは404で、存在しないものと区別できない（相談・メモ） | AU-12〜AU-16 | OK | A・B・C |
| 3 | リクエスト内の`user_id`を信じない | AU-17、AU-18 | OK | A・B |
| 4 | 未承認の内容・会話全文が残らない（DB・Redis・ログ・エラー応答） | NP-01〜NP-12、NP-19、SV-04 | OK（保存あり）／未確認（NP-19の保存なし） | A・C |
| 5 | Redisに保存するのは利用回数のキーだけ | 6.3手順4、NP-19 | OK（保存あり）／未確認（NP-19の保存なし。No.4参照） | A・C |
| 6 | DBのメモは暗号文だけ | SV-08、SV-10、SV-11、NP-09 | OK | A・C |
| 7 | 暗号文とユーザーID・メモIDの結び付け | SV-24、SV-13 | OK | A |
| 8 | ログ・エラー応答に本文・トークン・例外の詳細を出さない | NP-10、NP-11、NP-13〜NP-18 | OK（確認した範囲。NP-15の未確認の1点はNo.13） | A・B・C |
| 9 | 秘密情報がリポジトリ・ログに出ない | NP-13〜NP-15 | OK（確認した範囲。NP-15の未確認の1点はNo.13） | B・C |
| 10 | プロンプトインジェクション | AI-05、AI-12、AI-13 | OK（最低限の確認） | A・B |
| 11 | XSS・SQLインジェクション | なし（Q-03で作成） | OK | B・C |
| 12 | 退会後・退会処理中の拒否、退会でデータが消える | AU-19、AU-21、AU-22、SV-21〜SV-23 | OK（API）／未確認（画面） | A・B |
| 13 | 決済の例外で内部情報を出さない | NP-15 | 一部OK／未確認（1点） | A |
| 14 | 依存パッケージの脆弱性 | なし（もえさんの補足で追加） | NG（#119で相談） | `npm audit` |

NGは、No.14の1件だけ。No.1〜13で不具合は見つからなかった。未確認は、No.4・5（NP-19の保存なし）、No.12（画面）、No.13（1点）。

### 根拠

テストのパスは`backend/tests/features/`から書く（`core/`・`integrations/`は`backend/tests/`から）。

**No.1 認証**
- A：`auth/test_dependencies.py`（トークンなしはFirebase・DBを呼ばずに401、退会処理中は403、認証基盤の障害は503で詳細を出さない）、`integrations/firebase/test_client.py`、`core/test_errors.py`
- C：トークンなし（`GET /api/v1/memos`・`DELETE /api/v1/memos/{id}`）、不正なトークン（`GET /api/v1/usage`）は、どれも401。10/15の時点で仮の認証だった相談・利用回数のRouterは`get_current_user`に差し替わっていて、実際のFirebaseのトークンで相談・保存まで通った
- C：サービスアカウントに権限がない間は、画面に「現在サービスを利用できません」と表示され、操作は許可されなかった（認証基盤の障害として扱う。作りどおり）

**No.2 他人のデータ**
- A・B：メモの一覧のSQLは`user_id`で絞り込み、詳細・削除のSQLは`user_id`とメモIDの両方が条件（`read_db_repository.py`）。他人のメモと存在しないメモで同じ404（`memos/test_read_router.py::test_other_owner_and_absent_have_identical_404`、実DBの`test_read_db_repository.py`）。相談の一時状態も`user_id`で照合する（`consultations/test_router.py::test_other_user_and_missing_return_same_404`、`test_store.py`）。決済の確認も他人のSessionは404（`payments/test_router.py::test_confirm_others_session_is_404`）
- C：BからAのメモ詳細を開くと「このメモは表示できません。」と表示された（`MEMO_NOT_FOUND`＝404のときだけ出る文）。BのトークンでAのメモを`DELETE`すると404（ブラウザのコンソールでステータスを確認）。そのあとも、AのメモはDBに残っていた

**No.3 `user_id`を信じない**
- A・B：どのRouterも`user_id`をトークン（`Depends`）から取り、リクエストのスキーマに`user_id`はない。余分な項目は422（`core/test_errors.py::test_missing_and_extra_fields_return_422`）

**No.4 未承認の内容が残らない**
- A：相談の全体の流れで、本文がログに出ない（`consultations/test_privacy.py`）。AIの失敗で本文を返さない（`consultations/test_router.py::test_ai_failure_returns_502_without_content`）
- C：DBの書き出し・Redis・ログで、目印文字列は0件。ただし、方法Cで行った相談は2件とも保存した（NP-19の「保存あり」（SC-02）に当たる）
- **未確認（NP-19の保存なし）**：保存しないで終える流れ（SC-03）は、方法Cでは行っていない。自動テストでは、保存しないで終える流れで本文がログに出ないこと（`consultations/test_privacy.py::test_full_flow_does_not_log_consultation_content`）だけを確認している。引き継ぎ先：#62（MVP縦断・異常系のSC-03）。次の確認時期：#62の実施時

**No.5 Redis**
- A：利用回数のキーは、ユーザーIDごとの`count`・`period`だけ（`usage/test_limiter_redis.py`）。相談の一時状態はメモリに置き、Redisを使わない
- C：キーは`usage_limit:<内部ユーザーID>`の1つだけ（相談したのはAだけ）。種類はhashで、項目は`count`・`period`だけ。目印文字列は0件

**No.6 DBのメモは暗号文だけ**
- A：実DBで暗号文だけが入る（`memos/test_db_repository.py::test_concurrent_saves_create_one_row_with_ciphertext_only`）
- C：DBの書き出しで、目印文字列は0件（文字列・16進数とも）、`<script`も0件。`approved_memos`の列は、`id`・`user_id`・`source_consultation_id`・`encrypted_payload`（bytea）・`encryption_version`・`key_version`・`payload_version`・`approved_at`・`save_consented_at`・`created_at`だけで、平文の本文・理由の列はない。件数は保存した2件

**No.7 暗号文の結び付け**
- A：別のメモ・ユーザーへ移した暗号文と、別の鍵の暗号文を拒否する（`memos/test_service.py`の3件、`memos/test_router.py::test_ciphertext_moved_to_another_memo_is_500_without_details`、`memos/test_read_router.py::test_corrupt_or_moved_ciphertext_fails_whole_response`）。所有者の確認は復号の前（`memos/test_read_router.py::test_owner_check_happens_before_decryption`）

**No.8 ログ・エラー応答**
- B：developのログ出力をすべて確認した（10/15）。本文・トークン・Session ID・例外のメッセージを出しているものはなく、出すのは例外の種類・コード・内部ID（`payment_id`）・ステータスだけ。500は共通のミドルウェアで種類と場所だけ（`core/errors.py`）。アクセスログはオフ（`app/run.py`）
- C：backend・db・frontend・redisのログで、目印文字列・`eyJ`・`Bearer `は0件

**No.9 秘密情報**
- B：管理されているファイルに`.env`・鍵ファイルはなく、過去のコミット履歴にも追加されたことはない（`.env.example`だけ）。秘密鍵の形の文字列は、技術検証の置き換え用の値と「ログに出てはいけない文字列」の一覧だけで、本物の鍵ではない（10/12・10/15）
- C：暗号化の鍵、OpenRouterのキー、Firebaseの鍵のID、`BEGIN PRIVATE KEY`は、ログに0件

**No.10 プロンプトインジェクション**

もえさんの補足（10/12）のとおり、中心フローにかかわる最低限の確認を行った。詳しい追加の検証（攻撃文を多数試すなど）は行っていない。
- ユーザー入力とシステムの指示の分離（AI-12）：systemのメッセージは1つだけで、ユーザーの入力（命令文を含む架空の文）はuserのメッセージにだけ入る（`consultations/test_prompts.py::test_user_input_is_not_in_system_message`、`test_system_message_contains_only_server_values`、`consultations/test_service.py::test_user_input_is_sent_only_as_user_role`）
- AIの出力の検証（AI-05）：AIの出力のJSON Schemaは厳格で、モデルの項目と一致する（`consultations/test_ai_schemas.py::test_json_schema_is_strict_and_matches_model`）。余分な項目を含む出力は拒否する（`test_first_question_invalid`など）。検証エラーにAIの出力を含めない（`test_invalid_error_does_not_contain_ai_output`）
- サーバーが進め方を決める（AI-13）：話題の順番はサーバーが決め、AIが早く完了しようとしたり、最後の話題のあとで質問したりすると不正な出力として扱う（`consultations/test_service.py::test_guided_topics_follow_server_order`、`test_ai_completing_too_early_is_invalid`、`test_ai_asking_after_last_topic_is_invalid`、`consultations/test_ai_retry.py`の再試行の条件）。安全案内の文はAIの文ではなく固定の文を使う（`test_service.py::test_safety_on_start`）
- B：AIの出力をSQL・権限の判定に使う箇所はない（SQLはSQLAlchemyだけ。No.11）

**No.11 XSS・SQLインジェクション**
- B：フロントエンドに`dangerouslySetInnerHTML`・`innerHTML`・`document.write`・`eval`はない。`localStorage`・`sessionStorage`・`console.log`もない。バックエンドに文字列を組み立てて作るSQLはない（SQLAlchemyを使用）。`text()`はマイグレーションと部分インデックスの固定の値だけで、ユーザーの入力は入らない
- C：保存の理由に入れた`<script>alert(...)</script>`は、メモ詳細で文字として表示され、ダイアログは出なかった

**No.12 退会**

#60（PR #101）のテストを根拠として参照した。APIはOK、画面からの確認は未確認。

「APIはOK」は、自動テスト（Firebase・Stripeは模擬）とコードの確認による判断で、Firebase・Stripeを含む退会の実接続や、手動復旧のコマンドの実運用を確認したものではない（#60で実施範囲・持ち越し先を整理中）。方法Cでは退会を行っていない。
- 退会処理中は通常の操作ができない（AU-19）：`auth/test_dependencies.py::test_deleting_user_returns_403_without_details`、`payments/test_router.py::test_deleting_user_is_403`、`usage/test_consultation_start.py::test_deleting_user_is_rejected_and_key_deleted`
- 退会完了後のトークンで内部ユーザーが再作成されない（AU-21）：B。初回登録の検証は`check_revoked=True`で、Firebaseのユーザーが削除済みなら401になる（`auth/service.py`の`_register_locked`）。退会の検証も同じ（`users/deletion_service.py`、`users/test_deletion_firebase.py::test_deletion_verifier_passes_revocation_flag`）
- 退会完了後のトークンでは他のAPIを使えない（AU-22）：`payments/test_router.py::test_deleted_user_is_401`
- 退会で関連データが消え、他のユーザーのデータは残る（SV-21・SV-22）：実DBの`users/test_deletion_db.py::test_success_deletes_only_owner_and_related_rows`、`test_http_deletion_clears_real_redis_twice_and_preserves_other_user`
- 途中で失敗した場合（SV-23）：`users/test_deletion.py::test_failure_stops_and_retry_restarts`、`test_final_redis_failure_never_finishes`
- **未確認（画面）**：退会画面（#61）がまだないため、画面からの退会と、退会後のDB・Redisの確認はしていない。引き継ぎ先：#61（設定・ログアウト・退会画面）、#62（MVP縦断・異常系）。次の確認時期：#61のマージ後（10/25に着手するかを判断）

**No.13 決済**
- A：Session ID・Checkoutのページの情報をログに出さない（`payments/test_router.py::test_session_info_is_not_logged`、`test_service.py`・`test_confirm.py`・`test_settlement.py`の同名のテスト）。確認が必要な決済のログは`payment_id`だけ（`test_service.py::test_needs_review_log_has_payment_id_only`）。設定の誤り（Price ID）は固定の500（`test_router.py::test_invalid_price_is_fixed_500`）。Stripeにつながらないときは503（`test_confirm_stripe_unavailable_is_503`）
- **未確認（1点）**：NP-15のとおり、Stripeの例外のメッセージに目印を入れて、応答・ログに出ないことを確かめるテストは見つからなかった。例外のメッセージをログに出す書き方がないことは、No.8の方法Bで確認している。引き継ぎ先：#118（決済まわりの整理、最終提出の後）で、テストの追加を検討する

**No.14 依存パッケージ（PR #84で共有された分）**

10/23に、frontendのコンテナで`npm audit --omit=dev`を実行した（パッケージは変更していない）。critical 1件・high 5件。

| パッケージ | 重大度 | 内容 | アプリへの影響（10/23時点の判断） | 直し方 |
| --- | --- | --- | --- | --- |
| `next` 16.3.6（直接） | critical | Image Optimization APIや`use cache`のRCE、SSRF、キャッシュの汚染など10件 | アプリは`next/image`・`use cache`を使っていない。ただし`next`本体の問題で、criticalを含む | 16.4.3へ更新（メジャー更新なし） |
| `firebase`（直接）、`@grpc/grpc-js`・`@firebase/firestore`（`firebase`経由） | high | gRPCの証明書の扱いなど | アプリはFirestoreを使っておらず、Authenticationだけ | npmの修正案は古い版（9.14）へ戻すもので、採用しない |
| `sharp`（`next`経由） | high | librsvgの脆弱性 | アプリは`next/image`を使っていない | `next`の更新とあわせて確認 |

- 依存パッケージの更新は事前の承認が必要で（`AGENTS.md`）、#63の範囲外のため、この確認では更新していない
- **NG**：`next`のcriticalは、#119で、コード・資料の締切（10/28）の前に更新するかをチームに相談する（10/25までに決める。最終提出は10/30）
- PR #84の時点（high 6件）から、`next`のcriticalが増えている

## 4. MVPで対応しない制約

- バックエンドはリクエストごとのアクセスログを出さない（No.8のため）。そのため、方法Cの404は、画面の文とブラウザのコンソールのステータスで判断した
- 外部の脆弱性診断・本番環境への攻撃試験は行わない（#63の「やらないこと」）

## 5. 確認中に気づいたこと（不具合ではない）

- AIの整理結果は、入力をAIがまとめ直した文のため、目印文字列が落ちることがある。XSSの確認は、入力どおりに保存される「保存の理由」で行った
- 方法Cの準備で、ローカルの`backend/pyproject.toml`が空のフォルダになっていた（Gitの管理外。以前に別のブランチで起動したときにDockerが作ったものと思われる）。alembicが失敗するため削除した
- `firebase`を追加したあとは、`docker compose up --build`だけでは古い`node_modules`が残る（PR #84の既知の問題）。`--renew-anon-volumes`（`-V`）で作り直した

## 6. テスト設計書への変更案（るなさんへの提案。この文書では直さない）

- 6.3手順4・6.5のRedisの確認：利用回数のキーはハッシュ（`count`・`period`）になったため、`GET`ではなく`TYPE`・`HKEYS`・`HGETALL`で確かめる形に変える
- 6.1の表「利用回数」：「`usage_limit:{user_id}`の整数値のみ」→「`count`（整数）と`period`（期間ID）のみ」
- XSS：No.11の確認項目を追加する
- 6.2の目印文字列：AIがまとめ直す項目では目印が落ちることがあるため、入力どおりに保存される項目（保存の理由など）で確かめる、と補足する

## 7. 完了条件との照合（#63）

| 完了条件 | 状態 |
| --- | --- |
| 確認観点と結果を記録している | この文書 |
| 会話全文・平文・トークン・鍵が残らない | No.4・6・8・9でOK。ただし、NP-19の保存なし（No.4）とNP-15の1点（No.13）は未確認で、引き継ぎ先を記録した |
| 所有者確認をバックエンドで行っている | No.2・3でOK |
| 問題を不具合Issueへ切り分けている | No.14の`next`を#119へ |
| MVPで対応しない制約を記録している | 4章 |

# ぽろり。MVPテスト設計書

- 作成日：2026年9月26日
- 更新日：2026年9月29日
- ステータス：骨組みレビュー反映済み・5節作成中（確認担当レビュー前）
- 対応Issue：#16「MVPテスト設計書の初稿を作成する」
- 主担当：るな
- 確認担当：じま

## 1. 目的・対象範囲

実装完了後にテスト観点を考えるのではなく、MVP仕様と画面・API設計の初稿をもとに、正常系・異常系・セキュリティ・非保存確認の観点を先に整理する。Sprint3以降のテスト実装Issueと単体テストへ引き継ぐ。

### 対象に含める
- MVPの中心フロー（登録・ログイン〜相談〜扱い方の選択）。Issue #2の決定により、扱い方を選んだ時点で相談完了とし、保存は任意操作とする
- 必要に応じて行う、整理メモの保存・一覧・詳細・削除と、保存せず終了する操作
- 入力エラー、状態の矛盾、認証・認可、AI異常出力
- 暗号化・削除・非保存・ログ禁止
- Stripeテスト決済、Redisによる利用回数制限

### 対象に含めない
- テストコードの実装
- 全ブラウザ・全端末の網羅
- MVP外機能（伝え方メモ、会話練習、通知、RAG、メモ再編集など）
- 技術検証や設計で未確定の仕様を、本書で独自に確定すること

## 2. 前提・参照資料

本書は以下の資料（2026年9月27日時点）をもとにした初稿であり、設計の確定に合わせて更新する。

| 資料 | 関連Issue | 状態 |
| --- | --- | --- |
| docs/mvp-decisions.md、ワイヤーフレーム案、企画案 v0.3 | #2 | 確定 |
| docs/screen-design.md | #9 | 初稿・未マージ |
| docs/api-design.md | #10 | 初稿・未マージ |
| technical-verification/openrouter-model-comparison/ | #4 | マージ済み |
| technical-verification/auth-firebase-fastapi/ | #5 | マージ済み |
| technical-verification/stripe-test-payment/ | #6 | マージ済み |
| technical-verification/encryption-non-persistence/ | #7 | マージ済み |
| technical-verification/redis-usage-limit/README.md | #8 | マージ済み（TTL・複数ユーザーの分離・フェイルオープンを参照） |
| DB設計 | #11 | 初稿・未マージ（本書ではテーブル名を扱わない） |

### 期待結果の前提とする決定済みの方針

- 本人以外のデータ（メモ・相談セッション等）へのアクセスは、403ではなく404を返す。存在しないIDと区別しない（#5で検証済み、API設計で採用）
- `check_revoked` は `POST /users/me` でのみ使用する（API設計で決定）
- 開発環境と本番環境のログは、環境変数（`APP_ENV`、`LOG_LEVEL`等）によって出力内容を切り替える。実装・動作確認はSprint3で行う（講師回答済み）
- 利用回数は相談開始時（`POST /consultations`）に加算する（API設計で統一）。AI処理の失敗時などに加算を取り消すかは未確定（Q-04）

## 3. テスト区分・優先度・IDの定義

### 3.1 テスト区分

| 区分 | 内容 | 主な手段（想定） |
| --- | --- | --- |
| 単体 | 関数・スキーマ・APIハンドラ単位。DB・Redis・外部サービスはモック | pytest |
| 結合 | API＋PostgreSQL＋Redisを実物でつなぐ。AI（OpenRouter）・Stripe・Firebaseはモック | pytest＋Docker Compose |
| シナリオ | 画面操作でユーザーフローを通す。Firebase・Stripeテストモード・OpenRouterは実物を使い、外部サービスとの接続を確認する | 手動（ツールは要確認 Q-19） |

- 外部サービスとの接続そのものは技術検証（#4〜#8）で確認済みのため、結合テストでは自分たちのコードの分岐・保存・非保存を確認し、実物との接続はシナリオテストで確認する
- AIの異常出力（Schema違反、内容の破綻、安全案内の矛盾、タイムアウト等）は実物では狙って発生させられないため、モックを使った結合テストで確認する
- 外部APIを実物で呼ぶシナリオテストはCIとは分けて実施し、実施回数と費用の上限を事前に決めて記録する

### 3.2 優先度

| 優先度 | 基準 |
| --- | --- |
| P0 | MVP完成条件とスクールMUST要件に直結する。中心フロー、認証・認可、非保存、暗号化、安全案内（危機的な内容の検知時に通常の整理を止めること）に加え、Stripeテスト決済とRedis利用回数制限の要件を満たすことを示すテスト |
| P1 | 重要だが、P0の完了後でもよい。P0以外の異常系・境界値など |
| P2 | 余裕があれば実施する |

### 3.3 テストIDと分類ルール

| 接頭辞 | カテゴリ | 使用する節 |
| --- | --- | --- |
| SC | シナリオ（ユーザーフロー） | 4節のシナリオ一覧 |
| N | 正常系 | 5節の個別テスト項目 |
| V | 入力エラー | 5節の個別テスト項目 |
| ST | 状態の矛盾 | 5節の個別テスト項目 |
| AU | 認証・認可 | 5節の個別テスト項目 |
| AI | AI異常出力・安全案内 | 5節の個別テスト項目 |
| SV | 保存・削除・暗号化 | 5節の個別テスト項目 |
| NP | 非保存・ログ禁止 | 5節の個別テスト項目 |
| PY | 決済 | 5節の個別テスト項目 |
| RL | 利用回数制限 | 5節の個別テスト項目 |

- 単体・結合・シナリオの区分は、接頭辞ではなく5節の「区分」列で管理する
- 5節の分類ルール
  1. 機能カテゴリ（AU・AI・SV・NP・PY・RL）に当てはまる項目は、正常系・異常系を問わず機能カテゴリに入れる（例：決済成功はPY、他人のメモ取得はAU、メモ保存の成功はSV）
  2. N・V・STは、機能カテゴリに当てはまらない項目（相談フローの利用前の注意〜扱い方の選択、ホーム、設定など）に使う
  3. 複数のカテゴリに当てはまる場合は、期待結果で主に確かめたいことで1つに決め、他の観点は「観点」列に書く

### 3.4 表の書き方

- 1行に1ケースを書く。ただし、同じ検証を複数の値で行う場合は、パラメータ化して1行にまとめてよい（操作欄に対象の値を列挙する）
- 前提条件には、データの状態に加えて、モックが返す値や発生させる例外を書く。モックの戻り値は、返す項目と架空の値を最小限書く
- 前提条件の状態（status、question_count等）を作る方法は、相談中の一時状態の保持方式（Q-01）が決まるまで未確定とする
- 期待結果には、ステータスコード・レスポンス・画面表示を書く。結合・シナリオでは、DB・Redisの状態も書く
- 未確定の値は「要確認（Q-xx）」と書き、8節の番号と対応させる
- 文字数や上限値は固定値で書かず、「上限値」「上限＋1」のように書く

## 4. テスト対象フロー一覧

区分はすべてシナリオテスト。外部サービスは実物（Firebase・Stripeテストモード・OpenRouter）を使い、実施回数と費用の上限は7節に従う。

| ID | シナリオ | 対象画面 | 優先度 |
| --- | --- | --- | --- |
| SC-01 | 初回利用：新規登録してホームへ進み、利用前の注意（詳細）を確認して同意する | UI-001〜003 | P0 |
| SC-02 | 中心フロー（保存あり）：テーマ選択から扱い方の選択まで進め、整理メモを保存して詳細を確認する | UI-003〜009、011 | P0 |
| SC-03 | 中心フロー（保存なし）：扱い方の選択まで進め、保存せず終了してホームへ戻る。保存しなくても相談が完了する | UI-003〜009、002 | P0 |
| SC-04 | 相談を途中で中断し、ホームへ戻る。未承認の内容が保存されない | UI-006A〜E、002 | P0 |
| SC-05 | 保存メモの一覧・詳細を確認し、削除する | UI-010・011 | P0 |
| SC-06 | ユーザーBでログインし、ユーザーAのメモが一覧・詳細に表示されない | UI-001・010・011 | P0 |
| SC-07 | 危機的な内容を含む架空文を入力し、通常の整理を止めて安全案内に切り替わる。実物のAIでは同じ判定を再現できない可能性があるため、「通常の整理を継続しない」「固定テンプレートを使う」ことは5.5のモックを使った結合テスト（P0）で確認する（要確認 Q-09） | UI-005〜006E | P0 |
| SC-08 | 利用回数の上限に達した後、新しい相談を開始できず、プラン画面への導線が表示される（要確認 Q-03・Q-21） | UI-002・012 | P0 |
| SC-09 | Stripeテスト決済が成功し、確認後にプランが反映される（要確認 Q-02） | UI-012 | P0 |
| SC-10 | Stripeテスト決済をキャンセル、またはカード拒否した場合に、プランが変わらない（要確認 Q-02） | UI-012 | P0 |
| SC-11 | 退会すると保存メモが削除され、同じアカウントで利用できない（要確認 Q-15） | UI-013・001 | P0 |
| SC-12 | 出来事の訂正を上限まで行い、要約を直接編集して次へ進む | UI-006A・B | P1 |
| SC-13 | 「もう少し整理したい」を選び、追加質問を最大3問まで行う | UI-006A・B | P1 |
| SC-14 | 感情を「うまく言葉にできない」で回答して進む | UI-006C・D | P1 |
| SC-15 | 2回目以降の利用で、利用前の注意が短い表示になる | UI-003 | P1 |
| SC-16 | ログアウトして、再度ログインする | UI-013・001 | P1 |

## 5. テスト項目

表の見出しは全カテゴリ共通とする。

### 5.1 正常系（N）

相談フローの状態遷移を中心に書く。3.3の分類ルールに従い、機能カテゴリに当てはまる正常系は各カテゴリに記載する（内部ユーザーの作成・取得はAU、メモの保存・一覧・詳細・削除はSV、決済はPY、利用回数の加算・上限判定はRL）。ログイン・ログアウトはフロントエンドのFirebase SDKで行い、バックエンドのAPIがないため、シナリオテスト（SC-01・SC-16）で確認する。非保存の確認はNPで行うため、ここでは重複して書かない。

| ID | 観点 | 区分 | 優先度 | 前提条件 | 操作 | 期待結果 | 対象API・画面 | 関連Issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| N-01 | 利用前の注意への同意を記録できる | 結合 | P1 | ログイン済みのユーザーA。has_seen_notice=false | `has_seen_notice: true` を送信する | 200。レスポンスのhas_seen_noticeがtrue。DB上のユーザーAのhas_seen_noticeがtrueになる | `PATCH /users/me`、UI-003 | #2・#10 |
| N-02 | 相談テーマ6種類をすべて受け付ける | 単体 | P1 | なし | ThemeCategoryの値ごとにリクエストを検証する（パラメータ化：communication、lifestyle、money、care、future、other） | 6値すべてが検証を通過する | `POST /consultations` のリクエストモデル | #2・#10 |
| N-03 | 相談を開始できる | 結合 | P0 | ログイン済みのユーザーA。利用回数は上限未満。AIモックの戻り値：ai_question=「どんなことがありましたか？」（項目名は仮 Q-22） | テーマ `communication` と、目印入りの架空文を送信する | 201。consultation_id、status=`event_dialogue`、ai_question（モックの値）を返す | `POST /consultations`、UI-004・005 | #9・#10 |
| N-04 | 出来事の質問に回答できる | 結合 | P0 | status=`event_dialogue`、question_count=0、correction_count=0。AIモックの戻り値：ai_understanding=「連絡の返信が3日なかった」、ai_question=「そのとき何が一番気になりましたか？」（項目名は仮 Q-22） | action=`answer` で架空の回答を送信する | 200。status=`event_dialogue`、question_count=1、correction_count=0。ai_understanding・ai_question（モックの値）を返す | `POST /consultations/{id}/event-dialogue`、UI-006A | #2・#10 |
| N-05 | AIの理解を訂正できる | 結合 | P0 | status=`event_dialogue`、question_count=1、correction_count=0。AIモックの戻り値：ai_understanding=「連絡の返信が5日なかった」、ai_question=「そのとき何が一番気になりましたか？」（項目名は仮 Q-22） | action=`correct` で「実際は5日間でした」を送信する | 200。ai_understandingが修正後の内容（モックの値）になる。ai_question（モックの値）を返す。correction_count=1、correction_limit_reached=false。question_countは1のまま変わらない | `POST /consultations/{id}/event-dialogue`、UI-006A | #2・#10 |
| N-06 | 出来事の要約が完成する | 結合 | P0 | status=`event_dialogue`、question_count=1。AIモックの戻り値：event_details={what_happened=「連絡の返信が3日なかった」、what_bothered_me=「既読なのに反応がないこと」} | action=`answer` で架空の回答を送信する | 200。status=`event_summary_ready`、question_count=2、event_detailsの2項目（モックの値）、can_ask_more=trueを返す | `POST /consultations/{id}/event-dialogue`、UI-006A→006B | #2・#10 |
| N-07 | 要約を編集して感情の選択へ進める | 結合 | P0 | status=`event_summary_ready` | action=`proceed` で、what_happenedを編集したevent_detailsを送信する | 200。status=`emotion_selection`。編集後のevent_detailsが次の整理に引き継がれることは、感情入力の行（N-09）で確認する | `POST /consultations/{id}/event-summary/confirm`、UI-006B | #2・#10 |
| N-08 | 追加の質問を選んで出来事の対話に戻れる | 結合 | P1 | status=`event_summary_ready`、question_count=2、can_ask_more=true。AIモックの戻り値：ai_question=「ほかに気になったことはありますか？」（項目名は仮 Q-22） | action=`ask_more` を送信する | 200。status=`event_dialogue`、ai_question（モックの値）を返す | `POST /consultations/{id}/event-summary/confirm`、UI-006B→006A | #2・#10 |
| N-09 | 感情を自分の言葉で入力でき、編集後の要約が引き継がれる | 結合 | P0 | status=`emotion_selection`。N-07でwhat_happenedを編集済み。AIモックの戻り値：ai_response=「不安に近いのですね。違っていたら教えてください。」 | category=`anxious`、detail=架空の文を送信する | 200。status=`guided_dialogue`、ai_response（モックの値）を返す。AIモックへ渡された入力に、編集後のevent_details、category、detailが含まれる | `POST /consultations/{id}/emotion`、UI-006C・D | #2・#10 |
| N-10 | 「うまく言葉にできない」で感情の整理へ進める | 結合 | P1 | status=`emotion_selection`。AIモックの戻り値：ai_response=「不安に近いのですね。違っていたら教えてください。」 | category=`anxious`、cannot_verbalize=trueを送信する（detailは送らない） | 200。status=`guided_dialogue`、ai_response（モックの値）を返す。AIモックへ渡された入力にdetailが含まれない | `POST /consultations/{id}/emotion`、UI-006D | #2・#9・#10 |
| N-11 | 感情の選択肢8種類をすべて受け付ける | 単体 | P1 | なし | EmotionCategoryの値ごとにリクエストを検証する（パラメータ化：lonely、sad、anxious、angry、confused、hurt、self_blame、other） | 8値すべてが検証を通過する | `POST /consultations/{id}/emotion` のリクエストモデル | #2・#10 |
| N-12 | 本音・背景・望みの質問に回答できる | 結合 | P0 | status=`guided_dialogue`。AIモックの戻り値：ai_question=「その気持ちの背景には、どんな望みがありそうですか？」（項目名は仮 Q-22） | answer=架空の回答を送信する | 200。status=`guided_dialogue`、ai_question（モックの値）を返す | `POST /consultations/{id}/guided-dialogue`、UI-006E | #2・#10 |
| N-13 | 本音・背景・望みの整理が完了する | 結合 | P0 | status=`guided_dialogue`。AIモックは整理完了と、整理結果（event_summary、emotion、true_feeling、background、wish の架空の値）を返す（完了の判定方法は要確認 Q-13・Q-22） | answer=架空の回答を送信する | 200。status=`result_ready` | `POST /consultations/{id}/guided-dialogue`、UI-006E→007 | #2・#10 |
| N-14 | 整理結果を取得できる | 結合 | P0 | status=`result_ready`。N-13の整理結果が作成済み。backgroundは空文字 | 整理結果を取得する | 200。event_summary、emotion、true_feeling、background、wish（N-13の値）と、approved=falseを返す。backgroundは空文字のまま返る | `GET /consultations/{id}/result`、UI-007 | #9・#10 |
| N-15 | 整理結果の一部を編集できる | 結合 | P0 | status=`result_ready`、approved=false | wishだけを架空の文に変更して送信する | 200。wishが変更後の値になり、ほかの項目は変わらない。approved=falseのまま | `PATCH /consultations/{id}/result`、UI-007 | #2・#10 |
| N-16 | 整理結果を承認できる | 結合 | P0 | status=`result_ready`、approved=false、必須項目が入力済み | 承認する（ボディなし） | 200。status=`handling_selection`、approved=true | `POST /consultations/{id}/result/approve`、UI-007 | #2・#10 |
| N-17 | 扱い方を選択でき、相談が完了する | 結合 | P0 | status=`handling_selection`、approved=true | handlingの値ごとに送信する（パラメータ化：tell、hold、not_tell） | 3値とも200。status=`save_confirmation`。この時点で相談完了とする（保存は任意） | `POST /consultations/{id}/handling`、UI-008 | #2・#10 |
| N-18 | 保存せずに終了できる | 結合 | P0 | status=`save_confirmation` | 相談を削除する | 204。以後、同じconsultation_idの取得は404になる。DB・Redis・ログに内容が残らないことはNPで確認する | `DELETE /consultations/{id}`、UI-009→002 | #2・#10 |
| N-19 | 相談を途中で中断できる | 結合 | P0 | statusを状態ごとに用意する（パラメータ化：event_dialogue、event_summary_ready、emotion_selection、guided_dialogue、result_ready、handling_selection） | 相談を削除する | どの状態でも204。以後、同じconsultation_idの取得は404になる。未承認の内容が残らないことはNPで確認する | `DELETE /consultations/{id}`、UI-006A〜008→002 | #9・#10 |
| N-20 | 相談の途中状態を取得できる（再読み込み時の復帰） | 結合 | P1 | status=`event_dialogue`、question_count=1、correction_count=0 | 相談状態を取得する | 200。status、question_count、correction_count、直近のai_understanding・ai_questionを返す（A案〔クライアント保持〕を採用した場合、このAPIは成り立たないため要確認 Q-01） | `GET /consultations/{id}` | #9・#10 |

N-01をP1とする理由：同意の記録に失敗しても、相談の開始・完了は妨げられない（2回目以降に短い表示へ切り替わらないだけ）ため。初回利用の流れ全体は、SC-01（P0）で確認する。

### 5.2 入力エラー（V）

相談フローと利用前の注意の入力エラーを扱う。3.3の分類ルールに従い、所有者の偽装はAU、保存時の入力エラーはSV、エラーレスポンスへの送信値の混入はNPで扱う。

各行の期待結果には、次の共通の期待結果を含む。

- エラーレスポンスは共通のエラー形式で返る（要確認 Q-07）
- AIモックが呼び出されない
- 結合テストでは、相談の状態（status、question_count、correction_count、整理結果）が変わらない

| ID | 観点 | 区分 | 優先度 | 前提条件 | 操作 | 期待結果 | 対象API・画面 | 関連Issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V-01 | テーマが許容値の外 | 単体 | P1 | なし | themeを値ごとに送信する（パラメータ化：未定義の文字列、日本語の表示名、空文字、null、数値） | 422。detailsのfieldがtheme | `POST /consultations` | #2・#10 |
| V-02 | テーマが未指定 | 単体 | P1 | なし | themeを含めずに送信する | 422。detailsのfieldがtheme | `POST /consultations` | #10 |
| V-03 | 具体的な内容が空 | 単体 | P0 | なし | detailを値ごとに送信する（パラメータ化：空文字、空白のみ、改行のみ） | 422。detailsのfieldがdetail（空白・改行のみの扱いは要確認 Q-23） | `POST /consultations`、UI-005 | #9・#10 |
| V-04 | 具体的な内容が文字数の上限を超える | 単体 | P0 | なし | detailを上限＋1文字で送信する | 422。detailsのfieldがdetail（上限値は要確認 Q-14） | `POST /consultations`、UI-005 | #9・#10 |
| V-05 | 具体的な内容が文字数の上限ちょうど | 単体 | P1 | AIモックの戻り値：ai_question=「どんなことがありましたか？」 | detailを上限値ちょうどの文字数で送信する | 201。相談が開始される（上限値は要確認 Q-14） | `POST /consultations` | #9・#10 |
| V-06 | サーバー管理の項目を送信する | 単体 | P0 | なし | 正しいリクエストに項目を追加して送信する（パラメータ化：status、question_count、correction_count、approved） | 422。追加した項目は受け付けない | `POST /consultations`、`event-dialogue`、`result`（PATCH） | #10 |
| V-07 | 出来事の対話のactionが許容値の外 | 単体 | P1 | なし | actionを値ごとに送信する（パラメータ化：未定義の文字列、空文字、null） | 422。detailsのfieldがaction | `POST /consultations/{id}/event-dialogue` | #10 |
| V-08 | 回答が空 | 結合 | P0 | status=`event_dialogue`、question_count=1 | action=`answer` で、answerを値ごとに送信する（パラメータ化：空文字、空白のみ） | 422。question_countは1のまま（空白のみの扱いは要確認 Q-23） | `POST /consultations/{id}/event-dialogue`、UI-006A | #10 |
| V-09 | 訂正内容が空 | 結合 | P0 | status=`event_dialogue`、correction_count=0 | action=`correct` で、correction_inputを値ごとに送信する（パラメータ化：空文字、空白のみ） | 422。correction_countは0のまま | `POST /consultations/{id}/event-dialogue`、UI-006A | #10 |
| V-10 | actionと入力項目の組み合わせが不正 | 単体 | P1 | なし | 組み合わせごとに送信する（パラメータ化：answerなのにcorrection_inputだけ、correctなのにanswerだけ、両方を指定、どちらも未指定） | 422 | `POST /consultations/{id}/event-dialogue` | #10 |
| V-11 | 出来事の要約の必須項目が空 | 結合 | P0 | status=`event_summary_ready` | action=`proceed` で、項目ごとに空文字にして送信する（パラメータ化：what_happened、what_bothered_me） | 422。statusは`event_summary_ready`のまま | `POST /consultations/{id}/event-summary/confirm`、UI-006B | #10 |
| V-12 | 出来事の要約が文字数の上限を超える | 単体 | P1 | なし | 項目ごとに上限＋1文字で送信する（パラメータ化：what_happened、what_bothered_me） | 422（上限値はAPI設計の初稿値。最終値は要確認 Q-14） | `POST /consultations/{id}/event-summary/confirm` | #10 |
| V-13 | 要約確認のactionが許容値の外 | 単体 | P1 | なし | actionを未定義の文字列で送信する | 422。detailsのfieldがaction | `POST /consultations/{id}/event-summary/confirm` | #10 |
| V-14 | 感情が許容値の外 | 単体 | P1 | なし | categoryを値ごとに送信する（パラメータ化：未定義の文字列、日本語の表示名、空文字、null） | 422。detailsのfieldがcategory | `POST /consultations/{id}/emotion`、UI-006C | #2・#10 |
| V-15 | 感情の具体化が未回答 | 単体 | P0 | なし | detailを送らず、cannot_verbalize=falseで送信する | 422 | `POST /consultations/{id}/emotion`、UI-006D | #2・#10 |
| V-16 | 感情の具体化で両方を指定 | 単体 | P0 | なし | detail=架空の文、cannot_verbalize=trueで送信する | 422 | `POST /consultations/{id}/emotion`、UI-006D | #2・#10 |
| V-17 | 感情の具体化が空白のみ | 単体 | P1 | なし | detail=空白のみ、cannot_verbalize=falseで送信する | 422 | `POST /consultations/{id}/emotion`、UI-006D | #10 |
| V-18 | 感情の具体化が文字数の上限を超える | 単体 | P1 | なし | detailを上限＋1文字で送信する | 422（上限値はAPI設計の初稿値） | `POST /consultations/{id}/emotion`、UI-006D | #9・#10 |
| V-19 | 本音・背景・望みの回答が空 | 結合 | P0 | status=`guided_dialogue` | answerを値ごとに送信する（パラメータ化：空文字、空白のみ） | 422。statusは`guided_dialogue`のまま（空白のみの扱いは要確認 Q-23） | `POST /consultations/{id}/guided-dialogue`、UI-006E | #10 |
| V-20 | 整理結果の編集でapprovedを送信する | 結合 | P0 | status=`result_ready`、approved=false | wishの編集に、approved=trueを加えて送信する | 422。approved=falseのまま、wishも変わらない | `PATCH /consultations/{id}/result`、UI-007 | #10 |
| V-21 | 整理結果の必須項目を空にする | 結合 | P0 | status=`result_ready` | 項目ごとに空文字にして送信する（パラメータ化：event_summary、emotion、true_feeling、wish） | 422。整理結果は変わらない | `PATCH /consultations/{id}/result`、UI-007 | #10 |
| V-22 | 整理結果の背景は空でも受け付ける | 結合 | P1 | status=`result_ready`、backgroundに架空の値が入っている | background=空文字で送信する | 200。backgroundが空文字になる | `PATCH /consultations/{id}/result`、UI-007 | #9・#10 |
| V-23 | 整理結果が文字数の上限を超える | 単体 | P1 | なし | 項目ごとに上限＋1文字で送信する（パラメータ化：event_summary、emotion、true_feeling、background、wish） | 422（上限値はAPI設計の初稿値） | `PATCH /consultations/{id}/result` | #10 |
| V-24 | 扱い方が許容値の外 | 単体 | P1 | なし | handlingを値ごとに送信する（パラメータ化：未定義の文字列、日本語の表示名、空文字、null） | 422。detailsのfieldがhandling | `POST /consultations/{id}/handling`、UI-008 | #2・#10 |
| V-25 | 同意の値が真偽値でない | 単体 | P1 | なし | has_seen_noticeを値ごとに送信する（パラメータ化：文字列の"true"、数値の1、null） | 422（文字列や数値を真偽値に変換せず拒否する。StrictBoolを使う想定） | `PATCH /users/me`、UI-003 | #10 |
| V-26 | JSONの形式が不正 | 単体 | P1 | なし | 閉じ括弧のないJSONを送信する | 400（FastAPIの既定では422になるため、要確認 Q-24） | `POST /consultations` | #10 |
| V-27 | パスの相談IDが不正な形式 | 単体 | P1 | なし | UUID形式でない文字列をconsultation_idにして取得する | 422または404（要確認 Q-24） | `GET /consultations/{id}` | #10 |

### 5.3 状態の矛盾（ST）
### 5.3 状態の矛盾（ST）

相談の状態と操作が矛盾する場合を扱う。3.3の分類ルールに従い、保存時の状態の矛盾はSV、決済時はPY、退会時はAU・SVで扱う。

各行の期待結果には、次の共通の期待結果を含む（期待結果が200の行を除く）。

- エラーレスポンスは共通のエラー形式で返る（要確認 Q-07）
- AIモックが呼び出されない
- 相談の状態（status、question_count、correction_count、整理結果、approved）が変わらない

| ID | 観点 | 区分 | 優先度 | 前提条件 | 操作 | 期待結果 | 対象API・画面 | 関連Issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ST-01 | 追加質問が上限に達すると要約へ進む | 結合 | P0 | status=`event_dialogue`、question_count=2。AIモックの戻り値：event_details={what_happened=「連絡の返信が3日なかった」、what_bothered_me=「既読なのに反応がないこと」} | action=`answer` で架空の回答を送信する | 200。status=`event_summary_ready`、question_count=3、can_ask_more=false | `POST /consultations/{id}/event-dialogue`、UI-006A→006B | #2・#10 |
| ST-02 | 追加質問が上限に達した後は回答を続けられない | 結合 | P0 | status=`event_summary_ready`、question_count=3 | action=`answer` で架空の回答を送信する | 409。question_countは3のまま | `POST /consultations/{id}/event-dialogue` | #2・#10 |
| ST-03 | 追加質問が上限に達した後は「もう少し整理したい」を選べない | 結合 | P0 | status=`event_summary_ready`、question_count=3、can_ask_more=false | action=`ask_more` を送信する | 409。statusは`event_summary_ready`のまま | `POST /consultations/{id}/event-summary/confirm`、UI-006B | #2・#10 |
| ST-04 | 訂正が上限に達する | 結合 | P0 | status=`event_dialogue`、correction_count=1。AIモックの戻り値：ai_understanding=「連絡の返信が5日なかった」、ai_question=「そのとき何が一番気になりましたか？」（項目名は仮 Q-22） | action=`correct` で架空の訂正内容を送信する | 200。correction_count=2、correction_limit_reached=true | `POST /consultations/{id}/event-dialogue`、UI-006A | #2・#10 |
| ST-05 | 訂正が上限に達した後は訂正できない | 結合 | P0 | status=`event_dialogue`、correction_count=2、correction_limit_reached=true | action=`correct` で架空の訂正内容を送信する | 409。correction_countは2のまま。要約の直接編集（UI-006B）へ進むよう案内できるエラーを返す | `POST /consultations/{id}/event-dialogue`、UI-006A | #2・#10 |
| ST-06 | 訂正が上限に達した後の要約確認への進み方 | 結合 | P1 | status=`event_dialogue`、correction_limit_reached=true | UI-006Bへ進む操作を行う | 要約の直接編集ができる状態（`event_summary_ready`）になる（進み方は要確認 Q-25） | `POST /consultations/{id}/event-dialogue`、UI-006A→006B | #2・#9・#10 |
| ST-07 | 承認済みの整理結果は編集できない | 結合 | P0 | status=`handling_selection`、approved=true | wishを架空の文に変更して送信する | 409。整理結果は変わらない | `PATCH /consultations/{id}/result`、UI-007 | #10 |
| ST-08 | 承認済みの整理結果を再承認できない | 結合 | P0 | status=`handling_selection`、approved=true | 承認する（ボディなし） | 409。statusは`handling_selection`のまま | `POST /consultations/{id}/result/approve` | #10 |
| ST-09 | 必須項目が空のまま承認できない | 結合 | P0 | status=`result_ready`、approved=false。AIモックが返した整理結果のtrue_feelingが空文字 | 編集せずに承認する | 409。approved=falseのまま。空の項目を編集してから承認できる | `POST /consultations/{id}/result/approve`、UI-007 | #10 |
| ST-10 | 未承認のまま扱い方を選べない | 結合 | P0 | status=`result_ready`、approved=false | handling=`hold` を送信する | 409。statusは`result_ready`のまま | `POST /consultations/{id}/handling`、UI-008 | #2・#10 |
| ST-11 | 手順を飛ばしてAPIを呼べない | 結合 | P1 | 状態と呼び出すAPIの組み合わせを用意する | 組み合わせごとに呼び出す（パラメータ化：`event_dialogue`で`emotion`、`emotion_selection`で`guided-dialogue`、`guided_dialogue`で`result/approve`、`event_summary_ready`で`handling`） | 409。statusは変わらない | 相談フローの各API | #10 |
| ST-12 | 前の段階のAPIを呼べない | 結合 | P1 | 状態と呼び出すAPIの組み合わせを用意する | 組み合わせごとに呼び出す（パラメータ化：`guided_dialogue`で`event-dialogue`、`handling_selection`で`emotion`、`save_confirmation`で`handling`） | 409。statusは変わらない（画面の「戻る」操作との関係は要確認 Q-26） | 相談フローの各API | #9・#10 |
| ST-13 | 安全案内の状態では通常の整理を続けられない | 結合 | P0 | status=`safety_guidance` | 呼び出すAPIごとに送信する（パラメータ化：`event-dialogue`、`event-summary/confirm`、`emotion`、`guided-dialogue`、`result`のPATCH、`result/approve`、`handling`） | すべて409。statusは`safety_guidance`のまま。`DELETE /consultations/{id}` だけが204で成功する | 相談フローの各API | #4・#9・#10 |
| ST-14 | 削除済みの相談は操作できない | 結合 | P1 | `DELETE /consultations/{id}` で削除済み | 呼び出すAPIごとに送信する（パラメータ化：`GET /consultations/{id}`、`event-dialogue`、`result`のGET、`handling`、`DELETE /consultations/{id}`） | すべて404。存在しない相談IDと同じレスポンスを返す | 相談フローの各API | #10 |

### 5.4 認証・認可（AU）
### 5.4 認証・認可（AU）

内部ユーザーの作成・取得、トークンの検証、所有者の確認、退会後のアクセスを扱う。ログイン・ログアウトはバックエンドのAPIがないためSC（SC-01・SC-16）、決済の所有者確認とWebhookの署名検証はPY、退会時のデータ削除はSV、エラーレスポンスへのトークンの混入はNPで扱う。

結合テストでは、Firebaseの `verify_id_token` をモックにし、前提条件に戻り値（uid）または発生させる例外を書く。ユーザーA・Bは架空の検証用ユーザーとする。

| ID | 観点 | 区分 | 優先度 | 前提条件 | 操作 | 期待結果 | 対象API・画面 | 関連Issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AU-01 | 初回ログイン時に内部ユーザーが作成される | 結合 | P0 | Firebaseモック：uid=`user-a`を返す。DBにuser-aの内部ユーザーがない | 内部ユーザーの作成・取得を呼び出す | 201。user_idとhas_seen_notice=falseを返す。DBにfirebase_uid=`user-a`の内部ユーザーが1件作成される | `POST /users/me`、UI-001 | #5・#10 |
| AU-02 | 既存ユーザーは作成されず取得される | 結合 | P0 | Firebaseモック：uid=`user-a`を返す。DBにuser-aの内部ユーザーがある | 内部ユーザーの作成・取得を呼び出す | 200。既存のuser_idを返す。DBの内部ユーザーは1件のまま | `POST /users/me` | #5・#10 |
| AU-03 | 同じユーザーの作成が重複しない | 結合 | P1 | Firebaseモック：uid=`user-a`を返す。DBにuser-aの内部ユーザーがない | 内部ユーザーの作成・取得を同時に2回呼び出す | 2回とも成功（201または200）し、同じuser_idを返す。DBの内部ユーザーは1件だけ（firebase_uidの一意制約） | `POST /users/me` | #5・#11 |
| AU-04 | 削除済みユーザーは再作成されない | 結合 | P0 | Firebaseモック：uid=`user-a`を返す。user-aの内部ユーザーは削除済み（deleted） | 内部ユーザーの作成・取得を呼び出す | 403。内部ユーザーは新規作成されず、deletedのまま | `POST /users/me` | #5・#10 |
| AU-05 | トークンがないと認証が必要なAPIを使えない | 結合 | P0 | ユーザーAのメモ・相談が存在する | Authorizationヘッダーなしで呼び出す（パラメータ化：`POST /users/me`、`POST /consultations`、`GET /consultations/{id}`、`GET /memos`、`GET /memos/{id}`、`DELETE /memos/{id}`、`GET /usage`、`DELETE /users/me`、決済API） | すべて401。WWW-Authenticate: Bearerヘッダーを返す。Firebaseモックは呼び出されない。データは変わらない | 認証が必要な各API | #5・#10 |
| AU-06 | Bearer以外の形式を拒否する | 単体 | P1 | なし | `Authorization: Basic 架空の値` で呼び出す | 401。Firebaseモックは呼び出されない | 認証が必要な各API | #5 |
| AU-07 | 不正なトークンを拒否する | 結合 | P0 | Firebaseモック：InvalidIdTokenErrorを発生させる | 架空のトークンで呼び出す | 401。データは変わらない | 認証が必要な各API | #5 |
| AU-08 | 期限切れのトークンを拒否する | 結合 | P0 | Firebaseモック：ExpiredIdTokenErrorを発生させる | 架空のトークンで呼び出す | 401。データは変わらない | 認証が必要な各API | #5 |
| AU-09 | uidが不正なトークンを拒否する | 単体 | P1 | Firebaseモック：uidを値ごとに返す（パラメータ化：None、空文字、数値の123） | 架空のトークンで呼び出す | 401 | 認証が必要な各API | #5 |
| AU-10 | 認証基盤の障害時にアクセスを許可しない | 結合 | P0 | Firebaseモック：想定外の例外を発生させる、またはFirebaseの初期化に失敗させる（パラメータ化） | 架空のトークンで呼び出す | 503（要確認 Q-05）。アクセスを許可せず、データは変わらない。例外の詳細や設定情報をレスポンスに含めない | 認証が必要な各API | #5・#10 |
| AU-11 | 失効済みのトークンで内部ユーザーを取得できない | 結合 | P1 | Firebaseモック：RevokedIdTokenErrorを発生させる（check_revoked=Trueで呼ばれる） | 内部ユーザーの作成・取得を呼び出す | 401。Firebaseモックがcheck_revoked=Trueで呼ばれている | `POST /users/me` | #5・#10 |
| AU-12 | 他人の相談を操作できない | 結合 | P0 | ユーザーBの相談（status=`event_dialogue`）が存在する。Firebaseモック：uid=`user-a`を返す | BのconsultationIDを指定して呼び出す（パラメータ化：`GET /consultations/{id}`、`event-dialogue`、`result`のGET、`handling`、`save`、`DELETE /consultations/{id}`） | すべて404。Bの相談の状態は変わらない。AIモックは呼び出されない | 相談フローの各API | #5・#10 |
| AU-13 | 他人の相談と存在しない相談を区別できない | 結合 | P0 | ユーザーBの相談が存在する。Firebaseモック：uid=`user-a`を返す | Bの相談IDと、存在しない相談IDでそれぞれ取得する | どちらも404で、レスポンスの本文が同じ | `GET /consultations/{id}` | #5・#10 |
| AU-14 | 他人のメモを閲覧できない | 結合 | P0 | ユーザーBのメモが存在する。Firebaseモック：uid=`user-a`を返す | BのメモIDを指定して取得する | 404。メモの本文・所有者の情報を返さない。存在しないメモIDと同じレスポンス | `GET /memos/{id}`、UI-011 | #5・#10 |
| AU-15 | 他人のメモを削除できない | 結合 | P0 | ユーザーBのメモが存在する。Firebaseモック：uid=`user-a`を返す | BのメモIDを指定して削除する | 404。DB上のBのメモは削除されない | `DELETE /memos/{id}`、UI-011 | #5・#10 |
| AU-16 | メモ一覧に他人のメモが含まれない | 結合 | P0 | ユーザーA・Bがそれぞれメモを保存済み。Firebaseモック：uid=`user-a`を返す | メモ一覧を取得する | 200。Aのメモだけを返し、Bのメモは含まれない。件数にもBのメモは含まれない | `GET /memos`、UI-010 | #5・#10 |
| AU-17 | リクエストで所有者を偽装できない | 結合 | P0 | Firebaseモック：uid=`user-a`を返す | 正しいリクエストに、Bのuser_idまたはfirebase_uidを追加して送信する（パラメータ化：`POST /consultations`、`save`） | 422。相談・メモは作成されず、Bの所有物として保存されない | `POST /consultations`、`POST /consultations/{id}/save` | #5・#10 |
| AU-18 | 保存したメモの所有者がトークンのユーザーになる | 結合 | P0 | ユーザーAの相談がstatus=`save_confirmation`。Firebaseモック：uid=`user-a`を返す | 整理メモを保存する | 201。DB上のメモの所有者が、user-aに対応する内部ユーザーIDになる | `POST /consultations/{id}/save` | #5・#10 |
| AU-19 | 退会後のトークンではデータを操作できない | 結合 | P0 | ユーザーAは退会済み（内部ユーザーがdeleted）。Firebaseモック：uid=`user-a`を返す（退会前に発行されたトークンを想定） | 呼び出すAPIごとに送信する（パラメータ化：`POST /consultations`、`GET /memos`、`GET /usage`、決済API） | すべて403。データは返さず、変更もしない | 認証が必要な各API | #5・#10 |
| AU-20 | プラン一覧は認証なしで取得できる | 結合 | P2 | なし | Authorizationヘッダーなしでプラン一覧を取得する | 200。プラン一覧を返す | `GET /plans`、UI-012 | #10 |
| AU-21 | 改ざんされた相談の状態を受け付けない | 結合 | P1 | 相談中の一時状態をクライアントが保持する方式（A案）を採用した場合のみ | 状態（question_count、approved等）を書き換えて送信する | 拒否され、書き換えた状態で処理されない（採用可否と拒否時のステータスは要確認 Q-01） | 相談フローの各API | #10 |

### 5.5 AI異常出力・安全案内（AI）

AI呼び出しの失敗、不正な出力、安全案内を扱う。AIの異常出力は実物では狙って発生させられないため、すべてAIモックを使った結合テストで確認する（3.1）。AI失敗時の利用回数の扱いはRL（Q-04）、エラーレスポンス・ログへのAIの入出力の混入はNP、画面での入力内容の保持はSCで扱う。

AI呼び出しの失敗・不正な出力（AI-01〜AI-06）の期待結果には、次の共通の期待結果を含む。

- エラーレスポンスを返す（ステータスコード・エラーコードは要確認 Q-27）
- 相談の状態（status、question_count、correction_count、整理結果）が変わらない
- AIの出力（生の文字列）をそのままクライアントへ返さない

| ID | 観点 | 区分 | 優先度 | 前提条件 | 操作 | 期待結果 | 対象API・画面 | 関連Issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AI-01 | AI呼び出しがタイムアウトする | 結合 | P0 | status=`event_dialogue`、question_count=1。AIモック：タイムアウト例外を発生させる | action=`answer` で架空の回答を送信する | 共通の期待結果のとおり。question_countは1のまま（タイムアウト値は要確認 Q-10） | `POST /consultations/{id}/event-dialogue`、UI-006A | #4・#10 |
| AI-02 | AIの外部APIがエラーを返す | 結合 | P0 | status=`event_dialogue`、question_count=1。AIモック：エラーを返す（パラメータ化：HTTP 500、503、429、接続エラー） | action=`answer` で架空の回答を送信する | 共通の期待結果のとおり。question_countは1のまま | `POST /consultations/{id}/event-dialogue`、UI-006A | #4・#10 |
| AI-03 | AIの出力がJSONとして解析できない | 結合 | P0 | status=`guided_dialogue`。AIモックの戻り値：JSONでない文字列（例：「以下が回答です。」） | answer=架空の回答を送信する | 共通の期待結果のとおり | `POST /consultations/{id}/guided-dialogue`、UI-006E | #4・#10 |
| AI-04 | AIの出力がSchemaに違反する | 結合 | P0 | status=`guided_dialogue`。AIモックの戻り値：Schema違反のJSON（パラメータ化：必須項目の欠落、型の違い、定義外の項目、文字数の上限超過、必須の文字列が空） | answer=架空の回答を送信する | 共通の期待結果のとおり | `POST /consultations/{id}/guided-dialogue`、UI-006E | #4・#10 |
| AI-05 | AIの出力でサーバーの状態が変わらない | 結合 | P0 | status=`guided_dialogue`、approved=false。AIモックの戻り値：正しい出力に、status=`save_confirmation`・approved=trueを追加したJSON | answer=架空の回答を送信する | 共通の期待結果のとおり。statusとapprovedは、AIの出力に含まれた値で書き換わらない | `POST /consultations/{id}/guided-dialogue` | #10 |
| AI-06 | 再試行しても回数が二重に数えられない | 結合 | P1 | status=`event_dialogue`、question_count=1。AIモック：1回目はタイムアウト例外、2回目は正しい出力（ai_understanding、ai_question）を返す | action=`answer` で同じ回答を2回送信する | 1回目は共通の期待結果のとおり。2回目は200で、question_count=2（1回分だけ加算される。再試行時の数え方は要確認 Q-10） | `POST /consultations/{id}/event-dialogue`、UI-006A | #4・#10 |
| AI-07 | Schemaに合格しているが内容が破綻した出力 | 結合 | P1 | status=`guided_dialogue`。AIモックの戻り値：Schemaに合格するが、値が英語のメタ発言（例：「I don't need to output JSON」）の整理結果（#4でDeepSeekに実際に発生） | answer=架空の回答を送信する | 検出して不正な出力として扱うか、そのまま本人の確認・編集（UI-007）に委ねるか（要確認 Q-27） | `POST /consultations/{id}/guided-dialogue`、UI-006E・007 | #4・#10 |
| AI-08 | 安全案内に切り替わり、固定の文言を返す | 結合 | P0 | 相談の状態を、判定を行うAPIごとに用意する（パラメータ化：`POST /consultations`、`event-dialogue`、`emotion`、`guided-dialogue`。判定を行うAPIは要確認 Q-09）。AIモックの戻り値：risk_detected=true、continued_normal_structuring=false、safety_message=架空の電話番号を含む文 | 危機的な内容を含む架空文を送信する | 200。status=`safety_guidance`。safety_messageはサーバーの固定テンプレートの文言で、AIモックが返した文（架空の電話番号を含む）はレスポンスに含まれない | 相談フローの各API、UI-005〜006E | #4・#9・#10 |
| AI-09 | 安全案内の矛盾した出力を正規化する | 結合 | P0 | status=`guided_dialogue`。AIモックの戻り値：risk_detected=true、continued_normal_structuring=true（#4でgpt-oss-120bに実際に発生） | 危機的な内容を含む架空文を送信する | 200。status=`safety_guidance`。continued_normal_structuring=falseに正規化して返す。通常の整理の質問を返さない | `POST /consultations/{id}/guided-dialogue` | #4・#10 |
| AI-10 | 安全案内の出力自体が不正な場合 | 結合 | P0 | status=`guided_dialogue`。AIモックの戻り値：安全案内のSchemaに違反するJSON（safety_messageの欠落など） | 危機的な内容を含む架空文を送信する | 通常の整理に戻すか、安全側に倒して固定の安全案内を返すか（要確認 Q-28） | `POST /consultations/{id}/guided-dialogue` | #4・#10 |

### 5.6 保存・削除・暗号化（SV）
### 5.7 非保存・ログ禁止（NP）
### 5.8 決済（PY）
### 5.9 利用回数制限（RL）

## 6. 非保存確認の共通手順

## 7. テストデータ方針

- 実在の相談内容・個人情報は使用しない
- 本文には検出用の目印文字列（例：`PORORI_TEST_MARKER_001`）を含めた架空文を使う
- 決済はStripe公式のテストカードのみ使用する
- 認証は架空の検証用ユーザーA・Bを使う
- 外部サービスを実物で呼ぶシナリオテストはCIとは分けて実施し、実施回数と費用の上限を事前に決めて記録する（OpenRouterは課金あり）

## 8. 要確認事項一覧

「影響するテストID」は初稿作成中のため、3.3のカテゴリ接頭辞で記載する。カテゴリをまたいで横断的に影響する場合は、範囲を文章で記載する（例：エラーを扱うテスト全般）。5節の作成後に具体的なIDへ更新する。解消した項目も、番号を維持するため行は残す。

| No | 内容 | 関係Issue | 影響するテストID | 状態 |
| --- | --- | --- | --- | --- |
| Q-01 | 相談中の一時状態の保持方式（A:クライアント保持／B:APIプロセスのメモリ／C:Redis）。Cの場合、Redisの非保存確認の期待結果が変わる。Aの場合、クライアントから送られる状態の改ざん検知テストが必要になる | #10 | NP、SC、AU、ST | 未解決 |
| Q-02 | 決済方式（買い切り型／サブスク型）。サブスク型の場合、Webhook署名・冪等処理・解約の観点が加わる | #6・#10 | PY、AU | 未解決 |
| Q-03 | 価格・相談回数・保存件数の上限値、利用回数のリセット周期（TTL方式が第一候補） | #6・#8 | RL、SV | 未解決 |
| Q-04 | AI処理の失敗や安全案内で相談が早期終了した場合に、加算した利用回数を取り消すか | #10 | RL、AI | 未解決 |
| Q-05 | 認証基盤の障害・メモ保存失敗時のステータスコード（技術検証では503、API設計の一覧に503の記載なし） | #5・#7・#10 | AU、SV | 未解決 |
| Q-06 | 未承認・保存同意なしで保存しようとした場合のステータスコード（技術検証では400、API設計では409） | #7・#10 | ST、SV | 未解決 |
| Q-07 | エラーレスポンスの形式（技術検証では`{"detail": ...}`、API設計では`{"error": {...}}`） | #10 | エラーを扱うテスト全般 | 未解決 |
| Q-08 | Stripe API例外時のステータスコード（技術検証では400、API設計では500）。方針として、例外の中身（メッセージ・詳細）はレスポンスに返さない | #6・#10 | PY、NP | 未解決 |
| Q-09 | 危機的内容の判定方法と、判定を行うAPI | #4・#10 | AI | 未解決 |
| Q-10 | AI呼び出しのタイムアウト値・再試行回数、再試行時に質問数・訂正回数を加算するか | #9・#10 | AI、ST | 未解決 |
| Q-11 | 感情の選択肢は8種類が正だが、#4の検証用schema.jsonは7種類のまま | #4・#10 | V、AI | 未解決 |
| Q-12 | 整理結果・メモ詳細での「背景」の表示（画面設計では別項目で表示、API設計では表示要否が未定） | #9・#10 | N、SV、SC | 未解決 |
| Q-13 | 画面6-Eで「まだ分からない」「答えにくい」などの代替回答を設けるか、本音・背景・望みの質問数 | #9・#10 | V、N | 未解決 |
| Q-14 | 具体的な内容の文字数上限（画面設計では500文字、API設計では未記載） | #9・#10 | V | 未解決 |
| Q-15 | 退会時の処理順序、途中で失敗した場合の扱い、有料契約中の退会（409） | #10 | AU、SV、PY | 未解決 |
| Q-16 | 失効済みトークン・無効化ユーザーを拒否するタイミング。API設計で決定済み：`check_revoked` は `POST /users/me` でのみ使用する | #5・#10 | AU | 解消済み |
| Q-17 | 同意履歴・相談テーマをDBへ保存するか | #9・#11 | SV、NP | 未解決 |
| Q-18 | 開発環境と本番環境のログの出し分け。講師回答済み：環境変数（`APP_ENV`、`LOG_LEVEL`等）によって出力内容を切り替える。実装・動作確認はSprint3で行う | 企画案 §14 | NP | 解消済み |
| Q-19 | シナリオテストの実施手段（手動のみか、画面操作の自動化ツールを使うか）、フロントエンドのテストツール。3.1のテスト区分に影響する | 技術選定 | SC | 未解決 |
| Q-20 | 結合テストで外部サービス（AI・Stripe・Firebase）をモックにし、実物との接続はシナリオテストで確認する方針。レビューで合意済み（3.1・7節に反映）。Firebase Emulatorの採用は必要になった時点で再検討する | #16・技術選定 | AU、AI、PY、SC | 解消済み |
| Q-21 | 利用回数を加算するタイミング。最新のAPI設計で、相談開始時（`POST /consultations`）に統一された。失敗時の取り消しはQ-04で扱う | #8・#10 | RL、SV、N | 解消済み |
| Q-22 | AI出力のスキーマが、API設計で未定義。対象は、相談開始時の「最初の質問」、出来事の対話での「理解＋次の質問」、本音・背景・望みの対話での「次の質問」と「整理完了の判定」。5.1のモックの戻り値の項目名は仮とする | #4・#10 | N、AI | 未解決 |
| Q-23 | 空白・改行のみの入力を「空」として扱うか（API設計では、感情の具体化だけ空白を取り除いて判定している） | #9・#10 | V | 未解決 |
| Q-24 | JSONの形式不正（API設計では400だが、FastAPIの既定では422）と、パスのIDが不正な形式の場合のステータスコード（422か404か。404の場合、存在しないIDと区別しない方針との整合） | #10 | V、AU | 未解決 |
| Q-25 | 訂正が上限に達した後、要約確認（`event_summary_ready`）へどう進むか。サーバーが自動で要約を作るのか、クライアントが要約確認を要求するのか。上限到達後に`answer`は受け付けるか | #9・#10 | ST | 未解決 |
| Q-26 | 画面設計にある「戻る」操作（UI-006C→006B、UI-008→007、UI-009→008など）が、API設計の状態遷移にない。戻れるようにするか、戻る操作をなくすか | #9・#10 | ST、N、SC | 未解決 |
| Q-27 | AI処理の失敗（タイムアウト・外部APIのエラー・不正な出力）時のステータスコードとエラーコード（API設計では500の記載のみ）。Schemaに合格しても内容が破綻している出力（日本語でない、メタ発言など）を検出するか | #4・#10 | AI、NP | 未解決 |
| Q-28 | 安全案内の出力自体が不正（Schema違反など）な場合に、通常の整理へ戻すか、安全側に倒して固定の安全案内を返すか | #4・#10 | AI | 未解決 |

## 9. 完了条件チェック

- [ ] MVPの中心フローに正常系テストがある
- [ ] 主な入力エラー・APIエラー・AI異常出力の観点がある
- [ ] 認証・認可・別ユーザーアクセス拒否の観点がある
- [ ] 暗号化・削除・非保存・ログ禁止項目の確認がある
- [ ] Stripeテスト決済とRedis利用回数制限の観点がある
- [ ] 単体・結合・シナリオの区分と優先度が分かる
- [ ] 未確定仕様が関係Issueとともに明記されている

## 10. レビュー記録

| 日付 | 確認者 | 内容 | 対応 |
| --- | --- | --- | --- |
| 2026-09-27 | めぐ | 中心フローと保存の関係、P0の範囲、テストIDの用途、Q-18の講師回答、#8の参照先 | 1節・2節・3.2・3.3・8節に反映 |
| 2026-09-27 | じま | Q-20の合意と条件、3.4の書き方、分類ルール、Q-01・Q-07・Q-08・Q-16の更新、利用回数のタイミング（Q-21）、404方針 | 2節・3.1・3.3・3.4・7節・8節に反映 |
| 2026-09-29 | じま | 4節・5.1の粒度確認。event_detailsへの項目名修正、N-05〜N-07の期待結果、パラメータ化、モックの書き方、AI出力スキーマ（Q-22）、P0への安全案内の追加、ログイン・ログアウトの扱い、N-01の優先度 | 2節・3.2・3.4・4節・5.1・8節に反映 |
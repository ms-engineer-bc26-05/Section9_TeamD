## マイルストーン・スケジュール

更新日：2026年10月27日

## 共通前提

- MVPの中心は、ログイン後にAIとの相談で気持ちを整理し、本人が保存を承認した整理メモだけを扱うこと。
- 会話全文・入力原文・未承認内容をDB・Redis・ログへ永続保存しない。保存する整理メモは暗号化し、閲覧・更新・削除時は本人のデータであることを確認する。
- 安全案内とAI出力の検証を省略しない。実装済み・未実装・制約を区別して説明する。
- 日々の進捗は親Issue・子Issue・Pull Requestを正とする。この文書は全体日程、Sprintのゴール、レビュー日を確認する。
- 詳細Issueは原則として対象Sprintの開始前までに作成・確認する。日程・Sprintゴール・重要な依存関係が変わった場合は、別のドキュメント更新Issue・PRで本書を更新する。

## Sprint2までの実績と持ち越し

Sprint1（2026年9月7日〜9月17日）は、Issue・ソリューションの方向性、優先順位、習熟度、担当境界を確認する期間。

| 項目 | 実績・状態 |
| --- | --- |
| 共通環境 | 技術検証Issue [#3](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/3)・[#4](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/4)・[#5](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/5)・[#6](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/6)・[#7](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/7)・[#8](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/8)は完了。開発環境の最小構成はIssue [#32](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/32)、共通エラー・起動設定・README・構成整理はIssue [#35](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/35)がCLOSED。 |
| 技術選定 | Issue [#14](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/14)はCLOSED。検証結果と確定範囲は技術選定資料を参照する。 |
| 画面・API設計 | Issue [#9](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/9)・[#10](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/10)はCLOSED。実装に必要な仕様の最終整合は後続Issueで確認する。 |
| DB設計 | Issue [#11](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/11)はSprint2から持ち越し、10月3日にCLOSED。 |
| PRD・要件定義・テスト設計 | Issue [#12](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/12)・[#13](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/13)・[#16](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/16)はSprint2から持ち越し、#12・#16は10月6日、#13は10月24日にCLOSED。 |

Sprint2の期間は2026年9月18日〜9月26日。技術検証・技術選定と画面/APIの初稿は完了した一方、DB設計、PRD、要件定義、テスト設計および設計レビューは完了扱いにしない。

## Sprint3〜4

親Issue・子IssueはGitHubに登録済みです。Sprint3〜4の確認Issue [#33](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/33)は10月6日にCLOSED、計画PR [#37](https://github.com/ms-engineer-bc26-05/Section9_TeamD/pull/37)は10月6日にマージ済みです。表の状態は2026年10月27日時点です。

### Sprint3：2026年9月27日〜9月30日

**ゴール:** 後続実装を開始できる共通基盤を整え、API・DB・画面設計の実装に必要な部分、Issueの担当・範囲・依存関係、GitHub運用ルール、機能間契約を確認可能な状態にする。

| Issue | 内容 | 主担当 | 状態 |
| --- | --- | --- | --- |
| [#32](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/32) | 開発環境と最小アプリ基盤 | みほ | CLOSED |
| [#35](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/35) | 共通エラーハンドラ・起動設定・README・ディレクトリ構成 | みほ | CLOSED（PR #38を10月1日にマージ） |
| [#36](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/36) | 10/19アプリレビュー・STAGEに向けたIssue計画 | めぐ | CLOSED（10月6日） |
| [#44](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/44) | 親子Issueと担当・更新ルールをGitHub運用ルールへ追加 | めぐ | CLOSED（10月11日） |

設計の持ち越しはIssue [#11 DB設計](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/11)、[#12 PRD](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/12)、[#13 要件定義](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/13)、[#16 テスト設計](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/16)でした（いずれもCLOSED）。コーディング規約のIssue [#45](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/45)は、るなさんの稼働制約を踏まえてSprint5へ移しました。Formatter・Lintの選定・設定・CIはSprint4の[#46](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/46)でまとめて行い、その採用結果を#45で規約へ反映します。

### Sprint4：2026年10月1日〜10月5日

**ゴール:** CIを早期に導入し、認証・AI相談・相談画面・整理メモ保存を、共有済みの契約とモックを用いて並行実装する。中間レビューでは、その時点で安全に動作する範囲を確認する。中心フローの結合はSprint5の[#53](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/53)で行う。

| Issue | 内容 | 主担当 | 親Issue・状態 |
| --- | --- | --- | --- |
| [#46](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/46) | Formatter・Lint選定、共通設定と自動チェック | じま | #39・OPEN（Phase 1はマージ済み。Phase 2のPR #81は最終提出より持ち越し。10月27日に決定） |
| [#47](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/47) | Firebase認証と内部ユーザー基盤 | もえ | #40・CLOSED（10月15日） |
| [#48](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/48) | ログイン・ホーム・利用前注意 | るな | #40・OPEN |
| [#49](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/49) | 一時状態管理とAI相談の正常系API | みほ | #40・CLOSED（10月4日） |
| [#50](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/50) | 安全案内・回数上限・中断・一時状態破棄 | みほ | #40・CLOSED（10月10日） |
| [#51](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/51) | 相談開始から扱い方・保存選択まで | めぐ | #40・CLOSED（10月15日） |
| [#52](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/52) | 承認済み整理メモの暗号化保存 | じま | #40・CLOSED（10月13日） |

Epicは [#39 MVP](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/39) と [#40 中心相談フロー](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/40)。#47〜#52は#40配下、#46は#39配下です。#40はIssue #35の共通基盤を起点にし、認証・AI相談・メモ保存は共有済みの契約とモックを用いて並行します。特に#47の認証基盤を#49・#52から利用する関係など、詳細な依存は各Issueを参照してください。

- #46は2本のPRに分けて順番に進める。1本目（10月2日〜3日目安）でpytest・Next.jsビルドのCIを導入し、2本目でFormatter・Lintを追加する。
- #48は、るなさんが10月3日夜から着手する。認証済みAPI呼び出しの型・関数シグネチャは10月4日午前までに先行共有し、全体は10月6日頃の完了を目標とする。
- みほさんの担当は#49 → #50 → #57 → #54の順で進める。#49の正常系API契約・モックは10月2日頃までの先行共有を目標とし、#50は未完了の場合Sprint5前半へ継続する。

### 中間レビュー：2026年10月5日

- 10月5日に向けて実装を早期に打ち切らず、10月3日・4日も10月19日のMVP完成を目指して実装を進める。
- 中間レビュー専用の大規模な結合作業や発表資料作成は行わない。
- **10月5日:** 中間レビュー。その時点で安全に動作する範囲と、10月19日までの計画を説明する。

以下は10月19日のMVP完成に向けた優先順位です。P1が間に合わない見込みの場合は、担当者だけで対象外と決めずチームで対応を決めます。

**P0:** ログイン、利用前の注意、相談開始・入力、AI相談正常系、整理結果の確認・承認、「伝える・今は保留する・伝えない」の選択、安全案内、AI出力検証、会話全文・未承認内容を永続保存しないこと。

**P1:** 承認済み整理メモの暗号化保存、保存再試行時の二重保存防止、保存しない終了。

## Sprint5以降

Sprint5〜8の子Issue（#45、#53〜#71）は10月1日にGitHubへ登録済みで、範囲・担当は計画PR #37（10月6日マージ）で確定しました。下の表は当初の計画です。10月21日の見直しで日程が変わったため、Sprint8以降は「10月21日の見直しと最終提出までの日程」を正とします。

| 区分・期間 | 機能群と完了目標 |
| --- | --- |
| **Sprint5**<br>2026年10月6日〜10月11日 | ログインから整理メモ保存までの中心フロー結合（#53）、AIモデル最終確認・例外系・品質改善（#54）、保存メモ一覧・詳細・削除（#55・#56）、Redis利用回数制限・プラン判定（#57）、利用回数・プラン・決済画面（#58）、Stripe一回払いと利用権限反映（#59）、退会API・設定・ログアウト・退会画面（#60・#61）、コーディング規約の完成（#45）、必要な単体テストを完了する。Epic [#40](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/40)・[#41](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/41)。 |
| **Sprint6**<br>2026年10月12日〜10月18日 | 残機能、結合・シナリオテスト、認証・所有者確認、非保存・暗号化、安全案内・プロンプトインジェクション対策、秘密情報・ログ確認、README更新、MVP完成判定を行う。可能なら10月14日までに機能実装を終え、以降を品質確認に充てる。Canvaスライドのベース作成を開始する。Issue #62〜#65、Epic [#42](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/42)。 |
| **アプリレビュー**<br>2026年10月19日 | MVP中心機能を一連でデモし、実装済み・未実装・制約を説明する。一部モックがある場合はその範囲を明示する。 |
| **Sprint7**<br>2026年10月20日〜10月22日 | アプリレビュー指摘、各担当者の発表素材（#66〜#69）、Canva反映・発表原稿統合（#70）を進め、10月22日までにSTAGEスライド初版を完成させる。 |
| **スライドレビュー**<br>2026年10月22日 | スライド・デモ・担当・説明内容を確認する。 |
| **Sprint8**<br>2026年10月23日〜10月28日 | レビュー指摘、最終動作確認、スライド・原稿修正、リハーサルと改善記録（#71）、デモ・質疑応答練習を行う。10月25日を原則コードフリーズ、10月26日をSTAGEリハーサルとしてこの時点でアプリ・スライド・デモを完成させ、10月27日〜28日は指摘対応・緊急修正・最終確認のみとする。 |
| **STAGE本番**<br>2026年10月29日 | アプリ・スライド・デモ・説明を実施する。 |
| **修了式**<br>2026年10月30日 |  |

STAGE準備Epicは [#43](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/43)。日々の進捗と個別Issueの完了状態はGitHub上で確認してください。

## 10月21日の見直しと最終提出までの日程

10月21日に、最終提出までの優先順位と日程をチームで見直しました（めぐさんがDiscordで共有）。10月30日（金）は20時から修了式のため、10月29日までに提出できる状態にし、**10月28日（水）を実質のコード・資料の締切**とします。当初の「10月25日を原則コードフリーズ」は、この日程に置き換えます。

| 日付 | 内容 |
| --- | --- |
| 10月22日（木） | スライドレビュー。指摘事項を#65・#70へ整理する |
| 10月23日（金）〜25日（日） | PR・設計書のレビューとマージ、Stripeテストモードの確認、#62・#63の確認。10月25日に#61・#91の着手可否を判断する |
| 10月26日（月） | リハーサル。改善点・担当者・期限を[#71](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/71)へ記録し、「STAGE前必須」「最終提出まで」「持ち越し」に分類する |
| 10月27日（火） | リハーサルで判明した必須事項の修正。README・画面設計・API設計・テスト結果と実装の照合。子Issueの整理、親Issueの記録案、develop → mainのPRの準備 |
| **10月28日（水）** | **実質の締切**。必要なPRをdevelopへマージし、テスト・Build・起動を確認する。スライド・動画・台本・Q&Aを固定する。develop → mainのPRを作成し、作成者以外のApproveを受けてSquash and mergeする（難しい場合も、PR作成・CI・レビュー依頼までは終える） |
| 10月29日（木） | 未マージならdevelop → mainをマージし、mainで最終確認する。**STAGE本番**。子Issue・親Issue #39〜#43のClose・持ち越しを整理する |
| 10月30日（金） | 修了式。新規実装・大規模修正は行わず、提出物の確認と最終提出だけを行う |

### 10月28日までの最終作業計画（10月27日）

10月27日に、めぐさんが10月28日のdevelop → mainのマージに向けた計画を共有しました。最終提出の前は新しい実装を増やさず、提出物の正確性・テスト記録・セキュリティ対応・READMEの最新化を優先します。

| 順番 | PR | 内容 |
| --- | --- | --- |
| 1 | [PR #121](https://github.com/ms-engineer-bc26-05/Section9_TeamD/pull/121) | MVP縦断・異常系テストの結果（#62） |
| 2 | [PR #29](https://github.com/ms-engineer-bc26-05/Section9_TeamD/pull/29) | 本書（#15） |
| 3 | [PR #124](https://github.com/ms-engineer-bc26-05/Section9_TeamD/pull/124) | `next`の脆弱性の修正（#119） |
| 4 | [PR #113](https://github.com/ms-engineer-bc26-05/Section9_TeamD/pull/113) | README・デモ手順。PR #124の結果を踏まえてNext.jsの版などを確定する |
| 5 | develop → main | 対象のPRを整理した後、最後に作成する |

- PR #121とPR #29の順番は、作業状況に応じて前後してもよい。
- PR #124で問題が見つかり、10月27日夜までに原因を特定できない場合は、無理にマージせず、確認済みの範囲・未確認の事項・持ち越しの理由を記録して、10月28日の提出準備を優先する。
- PR #81（#46のPhase 2）は、変更範囲が大きく、Draftで、LintのCIも失敗しているため、mainへのマージの対象に含めない。

STAGE当日以降に修正が必要になった場合も、新機能は追加せず、発表・提出を止める重大な問題だけを、別Issue・作業ブランチ・PRで対応します。

### 最終提出より持ち越し（10月27日時点）

| 内容 | 記録先 |
| --- | --- |
| 状態不明で止まった決済（`creating`）の自動照合 | [#91](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/91)（10月25日に持ち越しと決定） |
| 退会の実接続確認（Stripe・Firebase・復旧CLI） | [#60](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/60)（PR #122はマージ済み）。後続Issueを作成予定 |
| プランの上限値の読み込み口の整理 | [#118](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/118) |
| `firebase`経由の依存パッケージのhigh 4件 | `docs/security-privacy-check.md`のNo.14 |
| Formatter・LintのCI（Phase 2、PR #81） | [#46](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/46)（10月27日に持ち越しと決定） |

設定・ログアウト・退会画面（[#61](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/61)）は、10月28日までに実装しません。未完成であることと後続の対応先を、README・Issueへ記録します（10月27日のめぐさんの計画）。

## 未確定事項・更新方法

- 進捗は親Issue・子Issue・PRを正とし、本書へ未完成の内容を完了済みとして記載しません。表の状態は更新日時点のものです。
- 個別Issueが追加されても、本書を都度更新する必要はありません。日程、Sprintゴール、重要な依存関係に変更がある場合は、別Issue・PRで更新します。
- 最終提出後の持ち越しは、各Issueと親Issue #39〜#43の記録を正とします。

## 参照

- Sprint3〜4 Issue確認: [#33](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/33)
- Sprint3〜8 Issue計画: [#36](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/36)、[PR #37](https://github.com/ms-engineer-bc26-05/Section9_TeamD/pull/37)
- 画面設計: [Issue #9](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/9)、[PR #25](https://github.com/ms-engineer-bc26-05/Section9_TeamD/pull/25)
- API設計: [Issue #10](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/10)、[PR #27](https://github.com/ms-engineer-bc26-05/Section9_TeamD/pull/27)
- DB設計: [Issue #11](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/11)、[PR #23](https://github.com/ms-engineer-bc26-05/Section9_TeamD/pull/23)
- PRD・要件定義: [Issue #12](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/12)、[Issue #13](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/13)
- 技術選定: [Issue #14](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/14)
- テスト設計: [Issue #16](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/16)、[PR #31](https://github.com/ms-engineer-bc26-05/Section9_TeamD/pull/31)
- マイルストーン更新: [Issue #15](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/15)、[PR #29](https://github.com/ms-engineer-bc26-05/Section9_TeamD/pull/29)


## マイルストーン・スケジュール

更新日：2026年10月2日

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
| DB設計 | Issue [#11](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/11)はOPEN。設計確認・レビューを持ち越す。 |
| PRD・要件定義・テスト設計 | Issue [#12](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/12)・[#13](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/13)・[#16](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/16)はOPEN。最新仕様との整合とレビューを継続する。 |

Sprint2の期間は2026年9月18日〜9月26日。技術検証・技術選定と画面/APIの初稿は完了した一方、DB設計、PRD、要件定義、テスト設計および設計レビューは完了扱いにしない。

## Sprint3〜4

親Issue・子IssueはGitHubに登録済みです。次の表は2026年10月2日時点の状態です。Sprint3〜4の確認Issue [#33](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/33)はOPENで、計画変更PR [#37](https://github.com/ms-engineer-bc26-05/Section9_TeamD/pull/37)もDraft・未Approveです。Issue番号・担当は登録内容を示し、Issue #33とPR #37の確認が終わるまでは、Sprintとの対応・依存関係を最終確定として扱いません。このマイルストーンの日程・ゴールは本Issueの依頼内容を基準にしています。

### Sprint3：2026年9月27日〜9月30日

**ゴール:** 後続実装を開始できる共通基盤を整え、API・DB・画面設計の実装に必要な部分、Issueの担当・範囲・依存関係、GitHub運用ルールとコーディング規約を確認可能な状態にする。

| Issue | 内容 | 主担当 | 状態 |
| --- | --- | --- | --- |
| [#32](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/32) | 開発環境と最小アプリ基盤 | みほ | CLOSED |
| [#35](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/35) | 共通エラーハンドラ・起動設定・README・ディレクトリ構成 | Issue上の担当記載なし | CLOSED |
| [#36](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/36) | 10/19アプリレビュー・STAGEに向けたIssue計画 | めぐ | OPEN |
| [#44](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/44) | 親子Issueと担当・更新ルールをGitHub運用ルールへ追加 | めぐ | OPEN |

設計の持ち越しはOPENのIssue [#11 DB設計](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/11)、[#12 PRD](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/12)、[#13 要件定義](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/13)、[#16 テスト設計](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/16)です。コーディング規約のIssue [#45](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/45)はGitHub上ではSprint5・OPENに分類されていますが、Sprint3の目標は規約を確認可能にすることです。どこまでをSprint3で確定するかは、Issue #33／PR #37の確認後に整合してください。

### Sprint4：2026年10月1日〜10月5日

**ゴール:** 認証・相談・整理メモ保存を縦断して実装し、中間レビューで安全に動作する範囲を確認できる状態にする。

| Issue | 内容 | 主担当 | 親Issue・状態 |
| --- | --- | --- | --- |
| [#46](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/46) | Formatter・Lint選定、共通設定と自動チェック | じま | #39・OPEN |
| [#47](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/47) | Firebase認証と内部ユーザー基盤 | もえ | #40・OPEN |
| [#48](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/48) | ログイン・ホーム・利用前注意 | るな | #40・OPEN |
| [#49](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/49) | 一時状態管理とAI相談の正常系API | みほ | #40・OPEN |
| [#50](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/50) | 安全案内・回数上限・中断・一時状態破棄 | みほ | #40・OPEN、Sprint4〜5 |
| [#51](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/51) | 相談開始から扱い方・保存選択まで | めぐ | #40・OPEN |
| [#52](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/52) | 承認済み整理メモの暗号化保存 | じま | #40・OPEN |

Epicは [#39 MVP](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/39) と [#40 中心相談フロー](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/40)。#47〜#52は#40配下、#46は#39配下です。#40はIssue #35の共通基盤を起点にし、認証・AI相談・メモ保存は共有済みの契約とモックを用いて並行します。特に#47の認証基盤を#49・#52から利用する関係など、詳細な依存は各Issueを参照してください。

### 中間レビュー：2026年10月5日

- **10月3日夜:** 機能実装の区切り。P1が間に合わない場合は、担当者だけで対象外と決めずチームで対応を決める。
- **10月4日:** 結合確認、不具合修正、README更新、シナリオ確認、デモ確認。レビュー準備をこの日までに完了する。
- **10月5日:** 中間レビュー。当日の予定実装は行わない。

**P0:** ログイン、利用前の注意、相談開始・入力、AI相談正常系、整理結果の確認・承認、「伝える・今は保留する・伝えない」の選択、安全案内、AI出力検証、会話全文・未承認内容を永続保存しないこと。

**P1:** 承認済み整理メモの暗号化保存、保存再試行時の二重保存防止、保存しない終了。

## Sprint5以降

詳細Issueは対象Sprintの開始前までに確認し、担当者が着手できる状態にします。Sprint5のIssue [#54](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/54)・[#55](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/55)・[#56](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/56)・[#57](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/57)・[#58](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/58)・[#59](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/59)・[#60](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/60)・[#61](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/61)はGitHub上に登録済みですが、計画PR #37が未確定のため、下記のゴールを優先し、個々のIssueの範囲・担当は確認完了時に確定します。

| 区分・期間 | 機能群と完了目標 |
| --- | --- |
| **Sprint5**<br>2026年10月6日〜10月11日 | 保存メモ一覧・詳細・削除、Redis利用回数制限、プラン条件、Stripe一回払いと利用権限反映、設定・ログアウト・退会、必要な単体テストを完了する。Epic [#41](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/41)。詳細Issueは10月5日までに確認し、10月6日から着手可能にする。 |
| **Sprint6**<br>2026年10月12日〜10月18日 | 残機能、結合・シナリオテスト、認証・所有者確認、非保存・暗号化、安全案内・プロンプトインジェクション対策、秘密情報・ログ確認、README更新、MVP完成判定を行う。可能なら10月14日までに機能実装を終え、以降を品質確認に充てる。STAGE資料の構成・素材整理を開始する。Epic [#42](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/42)。 |
| **アプリレビュー**<br>2026年10月19日 | MVP中心機能を一連でデモし、実装済み・未実装・制約を説明する。一部モックがある場合はその範囲を明示する。 |
| **Sprint7**<br>2026年10月20日〜10月22日 | アプリレビュー指摘、STAGEスライド、デモ手順、質疑応答資料、機能担当者の説明内容を整える。 |
| **スライドレビュー**<br>2026年10月22日 | スライド・デモ・担当・説明内容を確認する。 |
| **Sprint8**<br>2026年10月23日〜10月28日 | レビュー指摘、最終動作確認、スライド修正、デモ・質疑応答練習を行う。10月25日を原則コードフリーズ、10月26日をSTAGEリハーサルとし、10月27日〜28日は指摘対応・緊急修正・最終確認のみとする。 |
| **STAGE本番**<br>2026年10月29日 | アプリ・スライド・デモ・説明を実施する。 |
| **修了式**<br>2026年10月30日 |  |

STAGE準備Epicは [#43](https://github.com/ms-engineer-bc26-05/Section9_TeamD/issues/43)。日々の進捗と個別Issueの完了状態はGitHub上で確認してください。

## 未確定事項・更新方法

- Issue #33はOPEN、PR #37はDraft・未Approveです。Sprint3〜4の登録Issue番号・担当・親子関係は現時点のGitHub記録を掲載していますが、PR #37およびIssue #33の確認後に差異を反映します。
- Sprint2でOPENの設計Issue（#11〜#13・#16）は完了扱いにせず、レビュー・仕様調整の持ち越しとして扱います。
- Sprint5〜8の個別Issueが追加されても、本書を都度更新する必要はありません。日程、Sprintゴール、重要な依存関係に変更がある場合は、別Issue・PRで更新します。
- 進捗は親Issue・子Issue・PRを正とし、本書へ未完成の内容を完了済みとして記載しません。

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


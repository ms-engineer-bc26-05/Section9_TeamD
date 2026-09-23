# Stripeテスト決済 検証（買い切り型）

## 目的

StripeテストモードでCheckout Sessionを作成し、テストカードで決済を完了させ、
その支払い状態を`confirm_payment` APIのレスポンスでFastAPI側から確認できることを検証する。
（DB/Redisへの永続化は範囲外。詳細は「既知の制約」参照）
継続課金・解約・Webhookの本実装はこのIssueの範囲外とし、最小の買い切り型決済のみを検証する。

（依存Issue: `#2` / 後続Issue: `#10`, `#13`, `#14`）

---

## ① 最小決済フロー

買い切り型（`mode="payment"`）のみを対象とする。Webhookは使わず、
リダイレクト後にAPI経由でSessionの状態を同期的に確認する方式。

```
[ユーザー]                [FastAPI]                 [Stripe]
    |                         |                          |
    |--- 決済開始 ----------->|                          |
    |                         |--- Checkout Session作成 ->|
    |                         |<-- session_id / URL ------|
    |<-- Checkout画面へ遷移 --|                          |
    |                         |                          |
    |--- テストカード入力 --------------------------------->|
    |                         |                          |
    |<== 成功 / キャンセル / 失敗 のいずれかで戻る ==========|
    |                         |                          |
    | 成功時:                |                          |
    |  success_url へ ------->|                          |
    |                         |--- Session.retrieve ----->|
    |                         |<-- payment_status: paid --|
    |                         |--- {"status": "paid"} を返す（DB反映はしない）
    |                         |
    | キャンセル時:           |                          |
    |  cancel_url へ -------->|--- 状態は更新しない
    |                         |
    | 失敗時（カード拒否等）: |                          |
    |  Checkout画面内でエラー表示 → 状態は更新しない（未決済のまま）
```

**ポイント**
- `mode="payment"` を使う（`"subscription"` にしない）→ Webhookなしで完結できる。
- 成功判定は `success_url` へのリダイレクト時に `session_id` を受け取り、
  `stripe.checkout.Session.retrieve(session_id)` で `payment_status == "paid"` を確認してから反映する。
- 失敗（カード拒否）はCheckout画面内で処理され、アプリ側には基本的に遷移してこない
  （必要な場合のみエラー確認用に個別のテストカードで挙動を記録する）。

---

## ② 状態遷移メモ

| 状態 | 説明 | 遷移条件 |
|---|---|---|
| `unpaid`（未決済） | 初期状態。Checkout Session作成直後はこの状態 | ユーザーが決済フローを開始した時点 |
| `paid`（支払い済み） | `confirm_payment` APIが`{"status": "paid"}`を返す（DB/Redisへの保存はしない） | `success_url` 経由で `payment_status == "paid"` を確認できた場合のみ |
| `unpaid`（失敗のまま） | APIレスポンス上も状態は変化しない | `cancel_url` に遷移した場合、またはカード拒否などで決済が完了しなかった場合 |

**完了条件との対応**
- キャンセルまたは失敗時に有料状態へ更新されないこと → 上記の通り `paid` を返すのは
  `payment_status == "paid"` の確認が取れた場合のみに限定する。
- `paid`を返す判定はこの1箇所（`confirm_payment`内、成功時のみ）に集約し、他の経路からは返さない実装にする。

---

## ③ テストモードについて

- Stripeテストモードでのすべての操作について、実際の金銭のやり取りは発生しない。
- 使用するのはStripe公式のテスト用カード番号のみ。
  - 成功: `4242 4242 4242 4242`
  - 決済拒否（失敗確認用）: `4000 0000 0000 0002`
  - 有効期限・CVC・郵便番号はテストモードでは任意の値でよい（例: 有効期限は未来の日付、CVCは任意3桁）。
- 本番Stripeアカウントの審査・公開設定は行わない。
- 秘密鍵（`sk_test_...`）・Webhook secretは `.env` に格納し、`.gitignore` で除外してGitHubに含めない。

### 環境変数について

`.env`ファイルは以下の2箇所にあり、いずれも`.gitignore`で除外済み（`git check-ignore -v`で確認済み）。それぞれ値の無い（またはダミー値の）`.env.example`をリポジトリに含めているので、新規クローン時はこれをコピーして値を埋める。

| 場所 | 用途 | .env.example |
|---|---|---|
| `backend/.env` | `STRIPE_SECRET_KEY` | `backend/.env.example` あり |
| `stripe-test-payment/.env`（ルート直下） | `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `DATABASE_URL` / `REDIS_URL` | `stripe-test-payment/.env.example` あり |

`NEXT_PUBLIC_API_URL`（frontendがbackendを呼ぶ先）のみ、`.env`を介さず`docker-compose.yml`のfrontendサービスの`environment:`に直接記載している。frontend用の`.env`・`.env.example`は無い。

### 動作確認済みの修正

- `frontend/app/success/page.js`は`useSearchParams()`を使うため、Suspense境界なしでは`next build`時の静的プリレンダリングが失敗する（`next dev`では顕在化しない）。`useSearchParams()`を使う部分を`SuccessContent`コンポーネントに切り出し、`<Suspense>`でラップして解消済み（`docker compose exec frontend npm run build`で全ページの生成成功を確認済み）。

### 既知の制約（Webhook未使用方式について）

本Issueでは`success_url`リダイレクト後の`Session.retrieve`による同期確認方式を採用しているため、以下の制約がある。サブスク型やWebhookを使う実装に進む場合は解消が必要。

- ユーザーが決済成功後、`success_url`へ遷移する前にブラウザを閉じる・ネットワークが切断された場合、Stripe側は`payment_status: paid`でもアプリ側はそれを検知できない（Webhookを使わない構造上の既知の制約）。
- `GET /api/confirm-payment`は`session_id`を知っている人なら誰でも呼べる実装になっており、認証・ユーザー紐付けの検証をしていない。本番実装では「ログインユーザー本人のセッションかどうか」の検証が必須（後続Issueへの申し送り事項）。
- `/api/create-checkout-session`・`/api/confirm-payment`のテストが未追加。Stripe APIをモックして、①Session作成時に`mode="payment"`が指定されること、②`payment_status == "paid"`で`paid`を返すこと、③未決済状態で`unpaid`を返すこと、④Stripe例外時に適切なHTTPエラーを返すこと、を最低限確認するテストが必要（今回は手動確認のみ）。

---

## ④ Checkout Session作成の実行回数管理

作成上限は**最大6回**。テストモード以外への切り替えや実料金が発生する操作は行わない。

| # | 目的 | 使用テストカード | 結果 | 備考 |
|---|---|---|---|---|
| 1 | エンドポイント単体確認（Swagger UI） | - | 200、`cs_test_...`のSession URLを発行 | フロント実装前の疎通確認 |
| 2 | 画面ボタン→リダイレクト確認 | - | ボタン押下でCheckout画面へ遷移 | カード未入力 |
| 3 | 成功パターン確認 | `4242 4242 4242 4242` | `/success`で`{"status": "paid"}`を確認 | |
| 4 | キャンセルパターン確認 | （入力せず「戻る」） | `/cancel`に遷移、状態は更新されず | |
| 5 | 決済拒否（失敗）パターン確認 | `4000 0000 0000 0002` | Checkout画面内で「クレジットカードが拒否されました」と表示、`/success`へは遷移せず | |
| 6 | （予備・未使用） | | | 問題が出た場合の再実行用として温存 |

実行のたびに「結果」列を埋め、想定通りの状態遷移になっているかをここに記録する。

※ Checkout Sessionのline_item金額は、想定している有料プラン(月額300円)に合わせて `¥300` を例として使用する。本Issueでは`mode="payment"`の単発決済としてテストし、実際の月次課金(サブスク化)は別Issueで扱う。

---

## 買い切り型・サブスク型 追加実装比較メモ

このIssueでは買い切り型のみ実装する。サブスク型を選ぶ場合に追加で必要になる実装を整理しておく
（MVPでWebhook・解約が必要かどうかの判断材料）。

| 項目 | 買い切り型（本Issue） | サブスク型（未実装・比較用） |
|---|---|---|
| Checkout Session mode | `payment` | `subscription` |
| Price設定 | 単発の金額（本Issueのテストでは例として ¥300 を使用） | Priceオブジェクトに `recurring`（課金周期: 月次、¥300/月）を設定 |
| 支払い完了の検知 | `success_url` リダイレクト後に `Session.retrieve` で同期確認（Webhook不要） | Webhookが実質必須（`checkout.session.completed`, `invoice.paid` など）。リダイレクトだけでは継続課金の状態を追い切れない |
| 解約処理 | 不要 | `Subscription.cancel` 等の別実装が必要。解約タイミングの反映（即時 / 期間終了時）も要検討（月額300円プランを解約した月の扱いなど） |
| 失敗時の扱い | 都度のCheckoutが失敗するだけ | 更新時の支払い失敗（dunning）等、継続的なリトライ処理が別途必要になりうる |
| インフラ | Webhookエンドポイント不要 | Webhookエンドポイント・署名検証（`Webhook secret`）が必要 |

→ サブスク型は本Issueの範囲外とし、仕様決定後に別Issue化する。

### 追加で考慮すべき観点

| 観点 | 買い切り型（本Issue） | サブスク型（比較・未実装） |
|---|---|---|
| Webhookの冪等性 | 該当なし | Webhookはat-least-once配信のため再送されうる。同一イベントを二重処理しないよう、イベントIDの重複チェック等が必要 |
| ローカルでの検証手段 | `Session.retrieve`での同期確認のみで検証可能 | `stripe listen`（Stripe CLI）によるWebhookのローカル転送が開発時に必要になる |
| 返金（refund）時の状態反映 | 未整理。返金が発生した場合に有料状態をどう戻すか要検討 | 同様に未整理。特に期間途中解約時の返金ポリシーとあわせて検討が必要 |
| 二重決済防止 | 未実装。同一ユーザーが誤って複数回Checkout Sessionを作成した場合の重複購入防止は考慮されていない | サブスクの場合は「既に有効なサブスクがあるか」のチェックが同様に必要 |

### 結論・後続Issueへの申し送り

- 本Issueの完了条件（テストモードでの決済成功→アプリ側への反映）は、`confirm_payment` APIのレスポンスレベルでの確認までを対象とする（DB/Redisへの永続化は未実装。詳細は「既知の制約」参照）。
- サブスク型に進む場合、追加で必要になるのはWebhook受信基盤と解約フローの実装。Webhookは再送されうるため、イベントの冪等処理も合わせて設計する。
- 返金時の状態反映と、二重決済（重複Session作成）の防止は買い切り型・サブスク型どちらでも未整理のため、本実装に進む前に方針を決める。
- 料金・無料枠の最終決定と合わせて、サブスク化するかどうかは仕様決定後に別Issue（`#10`, `#13`, `#14`のいずれか）で判断する。

---

## 参考

- Stripe公式テスト用カード: Stripeドキュメントのテストカード一覧のみを使用する。
- 依存Issue: `#2`
- 後続Issue: `#10`, `#13`, `#14`

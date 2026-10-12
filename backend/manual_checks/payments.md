# 決済：止まった`creating`の行の片付け方（F-05 #59）

Checkout Sessionの作成で、Stripe側に作成されたかどうかを確認できなくなった決済の行（`payments.status = 'creating'`）を、手作業で片付ける手順。
Stripe上のSession一覧を検索して自動で照合する処理は、後続のIssue（#91）で扱う（#59で合意）。それまではこの手順で対応する。

- 担当：じま（F-05）。不在のときは、チームで担当を相談する
- 対象：Stripeの**テストモード**だけ。本番の鍵・本番のダッシュボードでは行わない
- Session ID・URL・秘密鍵・ユーザーIDを、Issue・PR・Discord・画面共有に貼らない。記録には決済ID（`payments.id`）と結果だけを書く

## どんなときに止まるか

決済の行は、同じ`idempotency_key`と保存した送信内容（`checkout_request`）でStripeを呼び直すことで、通常は自動で回復する（通信の失敗・タイムアウトでは止まらない）。
次の場合は、新しいSessionを作らずに止める（二重請求を防ぐため）。

- 同じキーで送った内容が前回と違うとStripeが返した（`StripeIdempotencyMismatch`）
- Sessionの有効期限（`expires_at`）をStripeが受け付けなかった（`StripeExpiresAtRejected`）

止まっている間、次のようになる。

| 場面 | 起きること |
| --- | --- |
| 購入ボタン（`POST /payments/checkout-session`） | 409 `CHECKOUT_IN_PROGRESS`が続く |
| 退会（`DELETE /users/me`） | 退会を始められない（#60の409）、または照合で止まる（`PaymentSettlementBlocked`） |

## 1. 止まった行を見つける

バックエンドのログに、決済IDと理由だけが出る（Session IDは出ない）。

```
checkout payment needs review: payment_id=<決済ID> reason=<例外の種類>
payment settlement blocked: payment_id=<決済ID> reason=creating
```

DBで行を確認する（開発環境の例。サービス名は実際の構成に読み替える）。

```bash
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
SELECT id, status, created_at, checkout_request->>'expires_at' AS expires_at
FROM payments
WHERE status = 'creating'
ORDER BY created_at;
SQL
```

## 2. Stripeのダッシュボードで確かめる

1. **`expires_at`を過ぎるまで待つ。** Sessionが作られていた場合も、`expires_at`を過ぎるとStripeが自動で期限切れにし、支払えなくなる。状態が動かなくなってから確かめる（そのため、この手順で`open`のSessionが見つかることはない。見つかった場合は直さずに相談する）
2. Stripeのダッシュボード（テストモード）で、行の`created_at`の前後に作られたCheckout Sessionを開き、metadataの`payment_id`が決済IDと一致するものを探す
3. 見つかった場合は、そのSessionの状態（`open`・`expired`・`complete`）と支払い状態を確かめる

## 3. 結果に合わせて行を直す

どの場合も、`WHERE status = 'creating'`を付けて、ほかの処理が進めた行を上書きしないようにする。1行だけ更新されたことを確かめてから`COMMIT`する。

| Stripeで確かめた結果 | 行の直し方 | その後 |
| --- | --- | --- |
| 支払い済み（`complete`・`paid`） | Session IDを保存して`pending`にする | 本人が決済の確認（`POST /payments/confirm`）か購入ボタンを押すと、確認へ進んで有料になる。退会処理中なら、照合で`paid`の記録だけが残る |
| 支払われずに期限切れ（`expired`） | Session IDを保存して`expired`にする | 本人はもう一度購入できる |
| 見つからない | **すぐには直さない。** `expires_at`を過ぎていて、同じ時間帯にこのユーザーの支払いもないことを確かめられた場合だけ`failed`にする | 本人はもう一度購入できる |

```sql
BEGIN;
-- 支払い済み・期限切れの場合（status は 'pending' か 'expired'）
UPDATE payments
SET status = 'expired', stripe_checkout_session_id = '<Session ID>', verified_at = now()
WHERE id = '<決済ID>' AND status = 'creating';
-- 見つからず、支払いもないと確かめた場合
-- UPDATE payments SET status = 'failed' WHERE id = '<決済ID>' AND status = 'creating';
-- 「UPDATE 1」と表示されたら COMMIT、それ以外なら ROLLBACK
COMMIT;
```

- Sessionが見つからないだけで「未作成・未決済」と決めない。確かめられない場合は、行を`creating`のまま残して止めておき、チームに相談する
- `pending`にするときは、`verified_at`を入れない（支払いの確認は`confirm`で行う）

## 4. 再開の条件

- 行が`creating`でなくなれば、購入ボタン・退会の再実行は通常どおり進む
- 片付けた結果（決済ID・どの場合だったか・日時）は、照合の後続Issue（#91）にコメントする

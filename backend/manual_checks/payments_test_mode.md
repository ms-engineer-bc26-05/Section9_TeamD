# 決済：テストモードでの実決済の確認（F-05 #59）

F-05の決済（Checkout Sessionの作成・決済の確認・利用権限の付与）が、実際のStripe（テストモード）とローカルのPostgreSQLで動くことを確かめる手順。
確認には`backend/scripts/check_stripe_payment.py`を使う。決済APIと同じサービスと実DBの実装を、架空のユーザーで呼ぶ（RouterのHTTPと認証は通らない。Routerの登録は結合Issue #53で行う）。

- 担当：じま（F-05）
- 対象：Stripeの**テストモード**だけ。本番の鍵・本番のダッシュボードでは行わない（スクリプトもテストモードの鍵以外では止まる）
- 秘密鍵・Session ID・決済画面のURL・ユーザーIDを、Issue・PR・Discord・画面共有に貼らない

## 確認すること

| ケース | 確認すること |
| --- | --- |
| 1. 成功 | 購入ボタンを2回押しても同じ決済画面が返る／支払う前は`pending`・無料のまま／テスト用カードで支払うと`paid`になり、有料の権限が付く／同じ`session_id`でもう一度確認しても`paid`（Stripeを呼ばない）／有料になった後の購入は409（`ALREADY_PAID`） |
| 2. キャンセル | 支払わずに戻ると`pending`・無料のまま／Sessionが期限切れになると`expired`・無料のまま／期限切れの後は新しい決済画面で買い直せる |

キャンセルのケースでは、35分の有効期限を待つ代わりに、スクリプトがStripeでSessionを期限切れにする（退会時の照合と同じ操作）。

## 1. 準備

1. Stripeのダッシュボードを**テストモード**に切り替える
2. 有料プラン用のPriceを確かめる（なければ作る）：**一回払い**（`one_time`）・有効（active）・通貨と金額は#59で決めた値
3. テストモードの秘密鍵（`sk_test_`）を用意する。制限付きキー（`rk_test_`）を使う場合の権限：Checkout Sessions（書き込み）、Prices（読み取り）
4. マイグレーションを適用しておく（`plans`に`premium`の行が必要）

```bash
docker compose run --rm --build backend alembic upgrade head
```

## 2. 実行

リポジトリのルートで実行する。鍵は`.env`やコマンドに書かず、画面に表示しない入力で渡す（シェルの履歴に残さないため）。

```bash
read -rs STRIPE_SECRET_KEY && export STRIPE_SECRET_KEY        # 秘密鍵を貼り付けて Enter（表示されない）
read -r STRIPE_PRICE_ID_PREMIUM && export STRIPE_PRICE_ID_PREMIUM  # Price ID（price_...）
docker compose run --rm --build -e STRIPE_SECRET_KEY -e STRIPE_PRICE_ID_PREMIUM \
  backend python -m scripts.check_stripe_payment
```

スクリプトが止まって決済画面のURLを表示したら、ブラウザで開いて操作する。

| ケース | ブラウザでの操作 |
| --- | --- |
| 1. 成功 | カード番号`4242 4242 4242 4242`、有効期限は未来の日付、CVCは任意の3桁、名前・メールは架空のもので支払う |
| 2. キャンセル | 支払わずに、左上の「←」（戻る）を押す |

戻った先の`localhost:3000`の画面は、フロントの決済画面（F-04）が未接続のため開けなくてよい。操作が終わったら、ターミナルで Enter を押す。

- すべて`PASS`なら、最後に「すべて PASS」と表示される
- `FAIL`・中断の場合は、そこで止まる。同じ鍵で何度も続けて実行せず、原因を確かめてから1回だけやり直す
- Stripeの呼び出しは1回の実行で15回（上限20回で止まる）
- 作った架空のユーザー・決済・利用権限は、終了時に削除される。ダッシュボードの確認のために残す場合は`--keep`を付ける

終わったら、シェルから鍵を消す。

```bash
unset STRIPE_SECRET_KEY STRIPE_PRICE_ID_PREMIUM
```

## 3. 記録

PRの本文（F-05）に、次の形式で書く。Session ID・URL・鍵・ユーザーIDは書かない。

```markdown
### テストモードでの実決済の確認

- 日時：2026-10-xx
- コミット：xxxxxxx
- 手順：backend/manual_checks/payments_test_mode.md
- 結果：

| ケース | 結果 |
| --- | --- |
| 1. 成功（同じ決済画面・pending・paid・権限の付与・再確認・409） | PASS |
| 2. キャンセル（pending・expired・買い直し） | PASS |

- Stripeの呼び出し：15回
- 確認していないこと：RouterのHTTP・認証を通した確認（#53の結合後）、フロントの成功画面・キャンセル画面（F-04）、Webhook（使わない）
```

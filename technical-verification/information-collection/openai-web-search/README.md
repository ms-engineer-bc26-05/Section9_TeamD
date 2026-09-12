# OpenAI APIのWeb検索機能を使う方法

担当：めぐ

## 目的

Responses APIのWeb検索機能を使い、Snow Man公式INFOページの最新5件について、公開日・タイトル・URLを取得できるか確認する。

## 最初に確認すること

今回利用を許可されている候補モデルは次の2つ。

- `gpt-5-nano`
- `gpt-4o-mini`

両モデルがResponses APIを利用できることは公式モデルページで確認できるが、Web検索機能への対応は明記されていない。そのため、最初の検証項目は「各モデルがWeb検索ツールを利用できるか」とする。

## 進め方

1. `OPENAI_API_KEY`が環境変数として設定されていることだけを確認する。値は画面に表示しない。
2. 通信しない事前確認を実行する。
3. `gpt-5-nano`を指定し、Web検索ツールを使うリクエストを1回実行する。
4. 成功、モデル非対応、権限不足、その他のエラーのいずれかを記録する。
5. 必要に応じて`gpt-4o-mini`でも1回実行する。
6. 取得できた場合は、最新5件を`result.json`へ記録する。
7. `baseline/latest-five.json`の目視確認結果と比較する。

## 実行方法

仮想環境を有効にする。

```bash
source technical-verification/information-collection/openai-web-search/.venv/bin/activate
```

API通信を行わない事前確認を実行する。

```bash
python technical-verification/information-collection/openai-web-search/search.py
```

`gpt-5-nano`でAPI通信を1回実行する。

```bash
python technical-verification/information-collection/openai-web-search/search.py --model gpt-5-nano --execute
```

必要な場合に応じて、`gpt-4o-mini`でAPI通信を1回実行する。

```bash
python technical-verification/information-collection/openai-web-search/search.py --model gpt-4o-mini --execute
```

`--execute`を付けない限り、OpenAI APIへのリクエストは送信されない。

4回目の最終検証ではAPI通信を120秒でタイムアウトし、Web検索は最大8回、SDKによる自動再試行は0回とする。タイムアウトした場合は繰り返し実行せず、エラーを`result.json`の検証履歴として記録する。

初回検証ではWeb検索自体は成功し、公開日とタイトルはおおむね取得できたが、記事詳細URLはすべて`null`だった。次の検証では検索対象ドメインを`mentrecording.jp`に限定し、各記事詳細ページを開くよう明示する。また、モデルの回答とは別に、Web検索が参照したURL一覧も取得して比較する。

API通信に成功した場合も失敗した場合も、APIキーを含まない結果だけを`result.json`へ自動追記する。

3回目の検証では、他の条件を変えず取得対象だけを最新1件に減らす。これにより、2回目のタイムアウトが5件の詳細ページ確認による負荷だったかを切り分ける。

4回目の検証では、取得対象を最新5件へ戻し、一覧ページと対象5件の詳細ページ以外を極力開かないよう制限する。120秒以内に安定して取得できるかを確認し、成功・部分成功・タイムアウトのいずれでも追加実行せず最終結果とする。

## 取得時の条件

- 公式INFOページを情報源として指定する。
- 最新5件の公開日・タイトル・URLを求める。
- 確認できない内容は推測せず、確認できないと回答させる。
- 回答に含まれた参照元URLも確認する。
- モデルがJSON内に返した記事URLと、APIが返した参照元URL一覧を分けて確認する。

## 完了条件

- 候補モデルでWeb検索ツールを利用できるか説明できる。
- 成功した場合は、最新5件の取得精度を確認できる。
- 失敗した場合は、APIキーを除いたエラーの種類と概要を記録できる。

## 公式ドキュメント

- [Web search](https://developers.openai.com/api/docs/guides/tools-web-search)
- [GPT-5 nano](https://developers.openai.com/api/docs/models/gpt-5-nano)
- [GPT-4o mini](https://developers.openai.com/api/docs/models/gpt-4o-mini)

## 注意事項

- APIキーをコード、結果JSON、README、スクリーンショットへ記載しない。
- 不必要に繰り返し実行しない。
- エラーも技術検証の結果として、そのまま記録する。

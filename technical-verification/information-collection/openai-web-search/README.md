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
2. `gpt-5-nano`を指定し、Web検索ツールを使うリクエストを1回実行する。
3. 成功、モデル非対応、権限不足、その他のエラーのいずれかを記録する。
4. 必要に応じて`gpt-4o-mini`でも1回実行する。
5. 取得できた場合は、最新5件を`result.json`へ記録する。
6. `baseline/latest-five.json`の目視確認結果と比較する。

## 取得時の条件

- 公式INFOページを情報源として指定する。
- 最新5件の公開日・タイトル・URLを求める。
- 確認できない内容は推測せず、確認できないと回答させる。
- 回答に含まれた参照元URLも確認する。

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

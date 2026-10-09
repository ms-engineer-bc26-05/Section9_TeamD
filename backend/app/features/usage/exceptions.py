"""利用回数制限の例外。

HTTPのステータス・エラーコードへの変換は http_errors.py で行う。
例外のメッセージに相談内容・ユーザーID・接続文字列を含めない。
"""


class NotAuthenticated(Exception):
    """認証できない（APIでは401）"""


class UsageLimitExceeded(Exception):
    """相談回数の上限を超えている（APIでは403・USAGE_LIMIT_EXCEEDED）"""


class PlanUnavailable(Exception):
    """DB障害などで利用権限（プラン）を確認できない（APIではエラー。無料・無制限とみなさない）"""


class MemoCountUnavailable(Exception):
    """保存メモの件数を取得できない（F-01・I-05の件数取得につなぐまでは常にこの状態）"""


class UsageStoreUnavailable(Exception):
    """Redisへ接続できない・応答がない。

    相談開始の判定ではフェイルオープンにするため外へ出さない。
    退会時のキー削除（F-06）では、再実行できるよう呼び出し元へ伝える。
    """

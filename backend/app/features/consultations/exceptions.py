"""相談機能の例外。

HTTPのステータス・エラーコードへの変換は http_errors.py で行う。
例外のメッセージに相談内容やAIの出力を含めない。
"""


class NotAuthenticated(Exception):
    """認証できない（APIでは401）"""


class ConsultationNotFound(Exception):
    """一時状態が存在しない、または本人のものでない（APIでは404）"""


class ConsultationBusy(Exception):
    """同じ相談の別のリクエストを処理中（APIでは409・CONSULTATION_BUSY）"""


class ConsultationStateConflict(Exception):
    """相談の状態と操作が矛盾している（APIでは409・CONSULTATION_STATE_CONFLICT）"""


class ResultNotReady(ConsultationStateConflict):
    """整理結果ができる前に取得しようとした（APIでは409・RESULT_NOT_READY）"""


class GuidedSkipNotAllowed(Exception):
    """背景以外の質問で「まだ分からない」（skipped）が指定された（APIでは422）"""

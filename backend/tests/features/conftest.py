"""機能のテスト全体の共通設定。

AI呼び出しの再試行（I-07 #54。app/features/consultations/ai_retry.py）は、既定では行わない。
既存のテストは「AIの失敗1回で502になる」ことを前提にしているため。
再試行のテストでは、ConsultationService に retry_policy を渡して有効にする
（tests/features/consultations/test_ai_retry.py）。
"""

import pytest

from app.features.consultations import ai_retry


@pytest.fixture(autouse=True)
def disable_ai_retry(monkeypatch):
    monkeypatch.setattr(ai_retry, "_policy_provider", lambda: ai_retry.NO_RETRY)

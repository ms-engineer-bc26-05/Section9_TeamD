"""相談機能のテストの共通設定。

相談開始（POST /consultations）には利用回数の判定（Issue #57）が組み込まれている。
相談機能のテストでは相談の動きだけを確認するため、利用回数の判定を「常に許可する」偽物へ
自動で差し替える（Redis・DBへは接続しない）。
利用回数を組み込んだ相談開始のテストは tests/features/usage/test_consultation_start.py で行う。
"""

import pytest

from app.features.usage import consultation_gate
from tests.features.usage.fakes import AllowAllStartGate


@pytest.fixture(autouse=True)
def allow_all_usage(monkeypatch):
    gate = AllowAllStartGate()
    monkeypatch.setattr(consultation_gate, "_gate_provider", lambda: gate)
    return gate

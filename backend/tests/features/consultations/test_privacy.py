"""相談内容をログ・エラーへ出さないことの確認。

正常系を一通りAPIで実行し、その間のログ（DEBUG以上）に、
相談本文・回答・AIの出力（すべて「架空」を含む）が出ていないことを確認する。
"""

import logging
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_exception_handlers
from app.features.consultations.router import get_current_user_id, router
from app.features.consultations.store import ConsultationStore, get_consultation_store
from app.integrations.openrouter.client import get_ai_client

from tests.features.consultations import fakes

BASE = "/api/v1/consultations"


def test_full_flow_does_not_log_consultation_content(caplog):
    caplog.set_level(logging.DEBUG)
    ai = fakes.FakeAIClient(
        [
            fakes.first_question(),
            fakes.event_ask(),
            fakes.event_summarize(),
            fakes.emotion_output(),
            fakes.guided_ask(),
            fakes.guided_complete(),
        ]
    )
    store = ConsultationStore()
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_consultation_store] = lambda: store
    app.dependency_overrides[get_ai_client] = lambda: ai
    user_id = uuid4()
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    client = TestClient(app)

    cid = client.post(BASE, json={"theme": "money", "detail": "架空の相談本文"}).json()[
        "consultation_id"
    ]
    requests = [
        ("post", "event-dialogue", {"action": "answer", "answer": "架空の回答"}),
        ("post", "event-dialogue", {"action": "answer", "answer": "架空の回答2"}),
        ("post", "event-summary/confirm", {"action": "proceed"}),
        ("post", "emotion", {"category": "angry", "detail": "架空の具体化"}),
        ("post", "guided-dialogue", {"answer": "架空の本音"}),
        ("post", "guided-dialogue", {"skipped": True}),
        ("patch", "result", {"wish": "架空の編集"}),
        ("post", "result/approve", None),
        ("post", "handling", {"handling": "not_tell"}),
    ]
    for method, path, payload in requests:
        response = getattr(client, method)(f"{BASE}/{cid}/{path}", json=payload)
        assert response.status_code == 200

    # 異常系（409・422）のエラー本文にも、送信した内容を含めない
    errors = [
        ("event-dialogue", {"action": "answer", "answer": "架空の遅い回答"}),  # 409
        ("guided-dialogue", {"answer": "架空の回答", "skipped": True}),  # 422
    ]
    for path, payload in errors:
        response = client.post(f"{BASE}/{cid}/{path}", json=payload)
        assert response.status_code in (409, 422)
        assert "架空" not in response.text

    assert client.get(f"{BASE}/{cid}").json()["status"] == "save_confirmation"
    assert "架空" not in caplog.text
    # 一時状態の repr にも相談内容が出ない
    assert "架空" not in repr(store._states)

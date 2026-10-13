"""保存メモのレスポンス型のテスト。DB・外部APIには接続しない。"""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError
import pytest

from app.features.memos.read_schemas import (
    MemoDetailResponse,
    MemoListItem,
    MemoListResponse,
)


def test_memo_list_response_serializes():
    memo_id = UUID("11111111-1111-4111-8111-111111111111")
    created_at = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)

    item = MemoListItem(
        memo_id=memo_id,
        created_at=created_at,
        summary="架空の出来事の要約",
        handling="hold",
    )
    response = MemoListResponse(memos=[item])

    assert response.model_dump(mode="json") == {
        "memos": [
            {
                "memo_id": str(memo_id),
                "created_at": "2026-10-10T12:00:00Z",
                "summary": "架空の出来事の要約",
                "handling": "hold",
            }
        ],
        "next_cursor": None,
    }


def test_memo_list_response_accepts_empty_list():
    response = MemoListResponse(memos=[])

    assert response.model_dump(mode="json") == {"memos": [], "next_cursor": None}


@pytest.mark.parametrize("reason", [None, "架空の選択理由"])
def test_memo_detail_response_serializes(reason):
    memo_id = UUID("11111111-1111-4111-8111-111111111111")
    created_at = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)

    response = MemoDetailResponse(
        memo_id=memo_id,
        created_at=created_at,
        event_summary="架空の出来事",
        emotion="寂しい",
        true_feeling="話を聞いてほしい",
        background="",
        wish="会話の時間を取りたい",
        handling="hold",
        reason=reason,
    )

    assert response.model_dump(mode="json") == {
        "memo_id": str(memo_id),
        "created_at": "2026-10-10T12:00:00Z",
        "event_summary": "架空の出来事",
        "emotion": "寂しい",
        "true_feeling": "話を聞いてほしい",
        "background": "",
        "wish": "会話の時間を取りたい",
        "handling": "hold",
        "reason": reason,
    }


@pytest.mark.parametrize(
    "extra_field",
    ["user_id", "firebase_uid", "encrypted_payload"],
)
def test_memo_list_item_rejects_extra_fields(extra_field):
    payload = {
        "memo_id": "11111111-1111-4111-8111-111111111111",
        "created_at": "2026-10-10T12:00:00Z",
        "summary": "架空の出来事の要約",
        "handling": "hold",
        extra_field: "dummy",
    }

    with pytest.raises(ValidationError) as caught:
        MemoListItem.model_validate(payload)

    assert [
        (error["loc"], error["type"])
        for error in caught.value.errors()
    ] == [((extra_field,), "extra_forbidden")]


def test_memo_list_response_rejects_extra_fields():
    with pytest.raises(ValidationError) as caught:
        MemoListResponse.model_validate(
            {"memos": [], "unexpected": "dummy"}
        )

    assert [
        (error["loc"], error["type"])
        for error in caught.value.errors()
    ] == [(("unexpected",), "extra_forbidden")]


@pytest.mark.parametrize(
    "extra_field",
    ["user_id", "firebase_uid", "encrypted_payload"],
)
def test_memo_detail_response_rejects_extra_fields(extra_field):
    payload = {
        "memo_id": "11111111-1111-4111-8111-111111111111",
        "created_at": "2026-10-10T12:00:00Z",
        "event_summary": "架空の出来事",
        "emotion": "寂しい",
        "true_feeling": "話を聞いてほしい",
        "background": "",
        "wish": "会話の時間を取りたい",
        "handling": "hold",
        "reason": None,
        extra_field: "dummy",
    }

    with pytest.raises(ValidationError) as caught:
        MemoDetailResponse.model_validate(payload)

    assert [
        (error["loc"], error["type"])
        for error in caught.value.errors()
    ] == [((extra_field,), "extra_forbidden")]


@pytest.mark.parametrize("handling", ["tell", "hold", "not_tell"])
def test_memo_list_item_accepts_valid_handling(handling):
    item = MemoListItem(
        memo_id=UUID("11111111-1111-4111-8111-111111111111"),
        created_at=datetime(2026, 10, 10, 12, 0, tzinfo=UTC),
        summary="架空の出来事の要約",
        handling=handling,
    )

    assert item.handling == handling


@pytest.mark.parametrize("handling", ["unknown", "", None, 1])
def test_memo_list_item_rejects_invalid_handling(handling):
    payload = {
        "memo_id": "11111111-1111-4111-8111-111111111111",
        "created_at": "2026-10-10T12:00:00Z",
        "summary": "架空の出来事の要約",
        "handling": handling,
    }

    with pytest.raises(ValidationError) as caught:
        MemoListItem.model_validate(payload)

    assert [
        (error["loc"], error["type"])
        for error in caught.value.errors()
    ] == [(("handling",), "literal_error")]


@pytest.mark.parametrize(
    ("handling", "valid"),
    [
        ("tell", True),
        ("hold", True),
        ("not_tell", True),
        ("unknown", False),
        ("", False),
        (None, False),
        (1, False),
    ],
)
def test_memo_detail_response_validates_handling(handling, valid):
    payload = {
        "memo_id": "11111111-1111-4111-8111-111111111111",
        "created_at": "2026-10-10T12:00:00Z",
        "event_summary": "架空の出来事",
        "emotion": "寂しい",
        "true_feeling": "話を聞いてほしい",
        "background": "",
        "wish": "会話の時間を取りたい",
        "handling": handling,
        "reason": None,
    }

    if valid:
        response = MemoDetailResponse.model_validate(payload)
        assert response.handling == handling
    else:
        with pytest.raises(ValidationError) as caught:
            MemoDetailResponse.model_validate(payload)

        assert [
            (error["loc"], error["type"])
            for error in caught.value.errors()
        ] == [(("handling",), "literal_error")]


@pytest.mark.parametrize(
    ("model", "required_fields"),
    [
        (MemoListItem, {"memo_id", "created_at", "summary", "handling"}),
        (MemoListResponse, {"memos"}),
        (
            MemoDetailResponse,
            {
                "memo_id", "created_at", "event_summary", "emotion",
                "true_feeling", "background", "wish", "handling", "reason",
            },
        ),
    ],
)
def test_memo_response_requires_fields(model, required_fields):
    with pytest.raises(ValidationError) as caught:
        model.model_validate({})

    assert {
        (error["loc"], error["type"])
        for error in caught.value.errors()
    } == {((field,), "missing") for field in required_fields}


@pytest.mark.parametrize("model", [MemoListItem, MemoDetailResponse])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("memo_id", "not-a-uuid"),
        ("created_at", "not-a-datetime"),
    ],
)
def test_memo_response_rejects_invalid_identifier_or_date(model, field, value):
    payload = {
        "memo_id": "11111111-1111-4111-8111-111111111111",
        "created_at": "2026-10-10T12:00:00Z",
        "handling": "hold",
    }
    if model is MemoListItem:
        payload["summary"] = "架空の要約"
    else:
        payload.update(
            event_summary="架空の出来事",
            emotion="寂しい",
            true_feeling="話を聞いてほしい",
            background="",
            wish="会話の時間を取りたい",
            reason=None,
        )
    payload[field] = value

    with pytest.raises(ValidationError) as caught:
        model.model_validate(payload)

    assert [error["loc"] for error in caught.value.errors()] == [(field,)]

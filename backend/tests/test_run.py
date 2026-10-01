"""起動処理（app/run.py）のテスト。

uvicorn.run をモックに置き換え、渡される設定だけを確認する。
"""

from app import run


def _capture(monkeypatch, reload_value: bool) -> dict:
    captured = {}
    monkeypatch.setattr(run, "BACKEND_RELOAD", reload_value)
    monkeypatch.setattr(run.uvicorn, "run", lambda *args, **kwargs: captured.update(kwargs))
    run.main()
    return captured


def test_reload_enabled(monkeypatch):
    kwargs = _capture(monkeypatch, True)

    assert kwargs["reload"] is True
    assert kwargs["workers"] == 1
    assert kwargs["access_log"] is False


def test_reload_disabled(monkeypatch):
    kwargs = _capture(monkeypatch, False)

    assert kwargs["reload"] is False
    assert kwargs["workers"] == 1
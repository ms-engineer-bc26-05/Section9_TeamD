"""アプリケーションへ中心フローのRouterが登録されていることを確認する。"""

from app.main import app


def test_core_flow_routes_are_registered_once() -> None:
    routes = [
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    ]

    expected_routes = [
        ("/api/v1/users/me", "POST"),
        ("/api/v1/users/me", "PATCH"),
        ("/api/v1/consultations", "POST"),
        ("/api/v1/consultations/{consultation_id}/save", "POST"),
        ("/api/v1/memos", "GET"),
        ("/api/v1/memos/{memo_id}", "GET"),
        ("/api/v1/memos/{memo_id}", "DELETE"),
        ("/api/v1/usage", "GET"),
        ("/api/v1/payments/checkout-session", "POST"),
        ("/api/v1/payments/confirm", "POST"),
        ("/api/v1/payments/me", "GET"),
    ]

    for expected_route in expected_routes:
        assert routes.count(expected_route) == 1
    assert not any(path.startswith("/api/v1/api/v1") for path, _ in routes)

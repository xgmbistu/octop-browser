"""Contract tests for the native ``GET /welcome`` HTTP route."""

from starlette.testclient import TestClient

from octop_browser.mcp_server import build_http_app


def test_welcome_returns_json() -> None:
    client = TestClient(build_http_app())
    response = client.get("/welcome")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"message": "welcome"}


def test_welcome_rejects_non_get() -> None:
    client = TestClient(build_http_app())
    assert client.post("/welcome").status_code == 405


def test_existing_sse_routes_are_preserved() -> None:
    paths = {getattr(route, "path", None) for route in build_http_app().routes}
    assert {"/sse", "/messages/", "/welcome"} <= paths

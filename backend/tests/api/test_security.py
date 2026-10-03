"""ローカル API の防御のミドルウェア単体のテスト（Design Doc 3-5-1）。

TestClient は ASGI のアプリを直接呼ぶので、HTTP のパーサ（uvicorn）は通らない。
Content-Length と実際の本文の食い違いなど、パーサが関わる点は、実物のサーバーで確かめる
（M6 の PR 3 の `vidcut serve`）。
"""

from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from vidcut.api.security import TOKEN_HEADER, ApiGuard, GuardSettings, local_guard, new_token

TOKEN = "t0ken-" + "x" * 37
BASE_URL = "http://127.0.0.1:8765"
LIMIT = 200


def make_app(settings: GuardSettings | None = None) -> FastAPI:
    app = FastAPI()

    @app.get("/")
    def index() -> HTMLResponse:
        return HTMLResponse("<html></html>")

    @app.get("/api/ping")
    def ping() -> dict[str, str]:
        return {"pong": "ok"}

    @app.post("/api/echo")
    def echo(body: dict[str, str]) -> dict[str, str]:
        return body

    @app.post("/api/act")
    def act() -> dict[str, bool]:
        return {"done": True}

    @app.get("/api/recordings/{recording_id}/proxy")
    def proxy(recording_id: str) -> dict[str, str]:
        return {"video": recording_id}

    app.add_middleware(
        ApiGuard, settings=settings or local_guard(TOKEN, port=8765, max_body_bytes=LIMIT)
    )
    return app


@pytest.fixture
def client() -> TestClient:
    """正しい Host とトークンを付けるクライアント。"""
    return TestClient(make_app(), base_url=BASE_URL, headers={TOKEN_HEADER: TOKEN})


def assert_refused(response: httpx.Response, status: int) -> None:
    assert response.status_code == status
    body = response.json()
    assert (body["success"], body["data"]) == (False, None)
    assert isinstance(body["error"], str) and body["error"]


class TestHost:
    def test_local_hosts_are_served(self, client: TestClient) -> None:
        assert client.get("/api/ping").json() == {"pong": "ok"}
        assert client.get("/api/ping", headers={"Host": "localhost:8765"}).status_code == 200

    @pytest.mark.parametrize(
        "host", ["evil.example:8765", "127.0.0.1:9999", "127.0.0.1", "localhost.evil.example:8765"]
    )
    def test_other_hosts_are_refused(self, client: TestClient, host: str) -> None:
        # DNS rebinding: 攻撃者のドメインが 127.0.0.1 を指しても、Host は攻撃者の名前のまま届く
        assert_refused(client.get("/api/ping", headers={"Host": host}), 403)

    def test_pages_outside_the_api_are_checked_too(self, client: TestClient) -> None:
        # 配信する HTML にはトークンを埋め込むので、HTML も別の Host には返さない
        assert client.get("/").status_code == 200
        assert_refused(client.get("/", headers={"Host": "evil.example:8765"}), 403)


class TestOrigin:
    @pytest.mark.parametrize("origin", ["http://127.0.0.1:8765", "http://localhost:8765"])
    def test_own_origin_is_served(self, client: TestClient, origin: str) -> None:
        assert client.post("/api/act", headers={"Origin": origin}).status_code == 200

    @pytest.mark.parametrize(
        "origin",
        ["http://evil.example", "null", "https://127.0.0.1:8765", "http://127.0.0.1:5173", ""],
    )
    def test_other_origins_are_refused(self, client: TestClient, origin: str) -> None:
        assert_refused(client.post("/api/act", headers={"Origin": origin}), 403)

    def test_development_origin_is_served_only_when_configured(self) -> None:
        settings = local_guard(TOKEN, port=8765, dev_origins=("http://localhost:5173",))
        client = TestClient(make_app(settings), base_url=BASE_URL, headers={TOKEN_HEADER: TOKEN})
        assert (
            client.get("/api/ping", headers={"Origin": "http://localhost:5173"}).status_code == 200
        )

    def test_no_cors_headers_are_sent(self, client: TestClient) -> None:
        response = client.get("/api/ping", headers={"Origin": "http://127.0.0.1:8765"})
        assert not [name for name in response.headers if name.lower().startswith("access-control")]


class TestToken:
    @pytest.fixture
    def anonymous(self) -> TestClient:
        return TestClient(make_app(), base_url=BASE_URL)

    def test_api_needs_the_token_header(self, anonymous: TestClient) -> None:
        assert_refused(anonymous.get("/api/ping"), 401)

    @pytest.mark.parametrize("token", ["", "wrong", TOKEN + "x", TOKEN[:-1], "トークン"])
    def test_wrong_tokens_are_refused(self, anonymous: TestClient, token: str) -> None:
        response = anonymous.get("/api/ping", headers={TOKEN_HEADER.encode(): token.encode()})
        assert_refused(response, 401)

    def test_pages_outside_the_api_need_no_token(self, anonymous: TestClient) -> None:
        assert anonymous.get("/").status_code == 200

    def test_token_in_the_query_is_not_accepted_for_the_api(self, anonymous: TestClient) -> None:
        assert_refused(anonymous.get("/api/ping", params={"token": TOKEN}), 401)

    def test_proxy_video_accepts_the_token_in_the_query(self, anonymous: TestClient) -> None:
        # <video> はヘッダーを付けられない（Design Doc 3-5-1）
        response = anonymous.get("/api/recordings/r1/proxy", params={"token": TOKEN})
        assert response.json() == {"video": "r1"}

    def test_proxy_video_refuses_a_wrong_or_missing_query_token(
        self, anonymous: TestClient
    ) -> None:
        assert_refused(anonymous.get("/api/recordings/r1/proxy", params={"token": "wrong"}), 401)
        assert_refused(anonymous.get("/api/recordings/r1/proxy"), 401)

    def test_proxy_video_also_accepts_the_header(self, client: TestClient) -> None:
        assert client.get("/api/recordings/r1/proxy").status_code == 200

    def test_only_the_proxy_path_takes_the_query_token(self, anonymous: TestClient) -> None:
        response = anonymous.get("/api/recordings/r1/proxy/extra", params={"token": TOKEN})
        assert_refused(response, 401)


class TestRequestBody:
    def test_json_is_accepted(self, client: TestClient) -> None:
        assert client.post("/api/echo", json={"a": "b"}).json() == {"a": "b"}
        response = client.post(
            "/api/echo",
            content=b'{"a": "b"}',
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "content_type", ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data"]
    )
    def test_other_content_types_are_refused(self, client: TestClient, content_type: str) -> None:
        # フォームから送れる形式を受け付けない（CSRF 対策）
        response = client.post(
            "/api/echo", content=b'{"a": "b"}', headers={"Content-Type": content_type}
        )
        assert_refused(response, 415)

    def test_body_without_a_content_type_is_refused(self, client: TestClient) -> None:
        assert_refused(client.post("/api/echo", content=b'{"a": "b"}'), 415)

    def test_request_without_a_body_needs_no_content_type(self, client: TestClient) -> None:
        assert client.post("/api/act").json() == {"done": True}

    def test_body_at_the_limit_is_accepted_and_over_it_refused(self, client: TestClient) -> None:
        def body(size: int) -> bytes:
            padding = size - len('{"a": ""}')
            return ('{"a": "' + "x" * padding + '"}').encode()

        headers = {"Content-Type": "application/json"}
        assert client.post("/api/echo", content=body(LIMIT), headers=headers).status_code == 200
        assert_refused(client.post("/api/echo", content=body(LIMIT + 1), headers=headers), 413)

    def test_body_of_unknown_length_is_refused(self, client: TestClient) -> None:
        def chunks() -> Iterator[bytes]:
            yield b'{"a": "b"}'

        response = client.post(
            "/api/echo", content=chunks(), headers={"Content-Type": "application/json"}
        )
        assert_refused(response, 411)

    def test_unreadable_content_length_is_refused(self, client: TestClient) -> None:
        response = client.post(
            "/api/echo",
            content=b"{}",
            headers={"Content-Type": "application/json", "Content-Length": "many"},
        )
        assert_refused(response, 400)

    def test_negative_content_length_is_refused(self, client: TestClient) -> None:
        response = client.post(
            "/api/echo",
            content=b"{}",
            headers={"Content-Type": "application/json", "Content-Length": "-1"},
        )
        assert_refused(response, 400)

    def test_reading_needs_no_content_type(self, client: TestClient) -> None:
        assert client.get("/api/ping", headers={"Content-Type": "text/plain"}).status_code == 200


class TestOtherScopes:
    def test_startup_and_shutdown_pass_through(self) -> None:
        # HTTP 以外（アプリの起動と終了の合図）は、確かめずにそのまま渡す
        with TestClient(make_app(), base_url=BASE_URL, headers={TOKEN_HEADER: TOKEN}) as client:
            assert client.get("/api/ping").status_code == 200


class TestNewToken:
    def test_tokens_are_long_and_different_each_time(self) -> None:
        first, second = new_token(), new_token()
        assert first != second
        assert len(first) >= 43  # 256 ビットを URL に使える文字で表した長さ
        assert local_guard(first, port=8765).token == first


class TestLocalGuard:
    def test_hosts_and_origins_follow_the_port(self) -> None:
        settings = local_guard(TOKEN, port=9000)
        assert settings.hosts == {"127.0.0.1:9000", "localhost:9000"}
        assert settings.origins == {"http://127.0.0.1:9000", "http://localhost:9000"}

    def test_refuses_a_token_too_short_to_be_random(self) -> None:
        with pytest.raises(ValueError, match="トークン"):
            local_guard("short", port=8765)

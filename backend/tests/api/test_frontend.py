"""ビルド済み frontend の配信（Design Doc 2 章・3-5-1）。HTML にはトークンを埋め込む。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import BASE_URL, TOKEN
from tests.pipeline.fakes import FakeMediaTool
from vidcut.api.app import ApiSettings, create_app
from vidcut.api.frontend import TOKEN_META
from vidcut.api.security import local_guard
from vidcut.bootstrap import build_api

INDEX = """<!doctype html>
<html lang="ja">
  <head>
    <meta charset="UTF-8" />
    <title>vid-cut</title>
  </head>
  <body><div id="root"></div><script type="module" src="/assets/app.js"></script></body>
</html>
"""
TOKEN_TAG = f'<meta name="{TOKEN_META}" content="{TOKEN}" />'


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    """ビルドの出力: index.html、assets/app.js、favicon.svg。その外に secret.txt。"""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX, encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('app');", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (dist / ".env").write_text("HIDDEN=1", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("SECRET", encoding="utf-8")
    return dist


def make_client(tmp_path: Path, dist: Path | None) -> TestClient:
    """トークンを付けないクライアント（ブラウザが最初にページを開くときと同じ）。"""
    home = tmp_path / "home"
    home.mkdir()
    api = build_api(home / "VidCut", media=FakeMediaTool())
    settings = ApiSettings(guard=local_guard(TOKEN, port=8765), home=home, frontend_dist=dist)
    return TestClient(create_app(api, settings), base_url=BASE_URL)


@pytest.fixture
def client(tmp_path: Path, dist: Path) -> TestClient:
    return make_client(tmp_path, dist)


class TestIndex:
    def test_page_carries_the_token_for_the_api(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert response.text.count(TOKEN_TAG) == 1
        assert response.text.index(TOKEN_TAG) < response.text.index("</head>")
        assert '<div id="root">' in response.text

    def test_page_with_the_token_is_not_stored(self, client: TestClient) -> None:
        # トークンは起動ごとに変わる。古いトークンの入ったページを、ブラウザに残さない
        assert client.get("/").headers["cache-control"] == "no-store"

    def test_paths_of_the_single_page_app_get_the_same_page(self, client: TestClient) -> None:
        for path in ("/lectures/abc123", "/index.html", "/no/such/page"):
            response = client.get(path)
            assert response.status_code == 200
            assert TOKEN_TAG in response.text

    def test_rebuilt_page_is_served_without_restarting(
        self, client: TestClient, dist: Path
    ) -> None:
        (dist / "index.html").write_text(INDEX.replace("vid-cut", "新しい版"), encoding="utf-8")
        assert "新しい版" in client.get("/").text

    def test_unknown_api_path_is_not_answered_with_the_page(self, client: TestClient) -> None:
        response = client.get("/api/nope", headers={"X-VidCut-Token": TOKEN})
        assert response.status_code == 404
        assert response.json()["success"] is False
        assert client.get("/api").status_code == 404

    def test_page_is_not_served_to_another_host(self, client: TestClient) -> None:
        # トークン入りの HTML を、DNS rebinding で読ませない
        response = client.get("/", headers={"Host": "evil.example:8765"})
        assert response.status_code == 403
        assert TOKEN not in response.text


class TestAssets:
    def test_built_files_are_served_as_they_are(self, client: TestClient) -> None:
        response = client.get("/assets/app.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]
        assert response.text == "console.log('app');"
        assert TOKEN not in response.text
        assert client.get("/favicon.svg").text == "<svg/>"

    @pytest.mark.parametrize(
        "path",
        [
            "/../secret.txt",
            "/%2e%2e/secret.txt",
            "/assets/../../secret.txt",
            "/assets/%2e%2e/%2e%2e/secret.txt",
            "//secret.txt",
        ],
    )
    def test_files_outside_the_build_are_not_served(self, client: TestClient, path: str) -> None:
        assert "SECRET" not in client.get(path).text

    def test_path_the_file_system_cannot_handle_gets_the_page(self, client: TestClient) -> None:
        response = client.get("/assets/a%00b.js")
        assert response.status_code == 200
        assert TOKEN_TAG in response.text

    def test_hidden_files_are_not_served(self, client: TestClient) -> None:
        assert "HIDDEN" not in client.get("/.env").text

    def test_link_that_leaves_the_build_is_not_served(
        self, client: TestClient, dist: Path, tmp_path: Path
    ) -> None:
        (dist / "assets" / "leak.txt").symlink_to(tmp_path / "secret.txt")
        assert "SECRET" not in client.get("/assets/leak.txt").text

    def test_folder_is_answered_with_the_page(self, client: TestClient) -> None:
        assert TOKEN_TAG in client.get("/assets").text


class TestWithoutBuild:
    @pytest.mark.parametrize("configured", [False, True])
    def test_explains_how_to_build_the_frontend(self, tmp_path: Path, configured: bool) -> None:
        client = make_client(tmp_path, tmp_path / "missing" if configured else None)
        response = client.get("/")
        assert response.status_code == 503
        assert "npm" in response.text
        assert TOKEN not in response.text
        # API は frontend がなくても使える
        assert client.get("/api/lectures", headers={"X-VidCut-Token": TOKEN}).status_code == 200

    def test_page_without_a_head_cannot_carry_the_token(self, tmp_path: Path, dist: Path) -> None:
        (dist / "index.html").write_text("<html><body></body></html>", encoding="utf-8")
        response = make_client(tmp_path, dist).get("/")
        assert response.status_code == 503
        assert TOKEN not in response.text


class TestSecurityHeaders:
    @pytest.mark.parametrize("path", ["/", "/assets/app.js", "/api/lectures"])
    def test_every_response_limits_what_the_browser_may_do(
        self, client: TestClient, path: str
    ) -> None:
        headers = client.get(path).headers  # /api はトークンなしで 401。断る応答にも付く
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["referrer-policy"] == "no-referrer"  # proxy の ?token= を外へ送らない
        assert headers["x-frame-options"] == "DENY"
        policy = headers["content-security-policy"]
        assert "default-src 'self'" in policy
        assert "frame-ancestors 'none'" in policy
        assert "script-src" not in policy or "'unsafe-inline'" not in policy.split("script-src")[1]

    def test_startup_and_shutdown_pass_through(self, tmp_path: Path, dist: Path) -> None:
        with make_client(tmp_path, dist) as client:
            assert client.get("/").status_code == 200

    def test_refusals_by_the_guard_carry_the_headers_too(self, client: TestClient) -> None:
        response = client.get("/", headers={"Host": "evil.example:8765"})
        assert response.headers["x-content-type-options"] == "nosniff"

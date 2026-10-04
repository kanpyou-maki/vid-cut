"""ビルド済み frontend の配信（Design Doc 2 章・3-5-1）。HTML にはトークンを埋め込む。"""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import BASE_URL, TOKEN
from tests.pipeline.fakes import FakeMediaTool
from vidcut.api.app import ApiSettings, create_app
from vidcut.api.frontend import TOKEN_META
from vidcut.api.headers import WAVEFORM_STYLE_HASH
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
# 波形の部品が差し込む style 要素のハッシュ。frontend のテストも、同じファイルを読む
WAVEFORM_STYLE_HASH_FILE = Path(__file__).with_name("waveform_style_hash.json")


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
        for path in ("/lectures/abc123", "/index.html", "/no/such/page", "/lectures/v1.2"):
            response = client.get(path)
            assert response.status_code == 200
            assert TOKEN_TAG in response.text

    def test_rebuilt_page_is_served_without_restarting(
        self, client: TestClient, dist: Path
    ) -> None:
        (dist / "index.html").write_text(INDEX.replace("vid-cut", "新しい版"), encoding="utf-8")
        assert "新しい版" in client.get("/").text

    def test_api_route_with_the_wrong_method_is_still_refused_as_such(
        self, client: TestClient
    ) -> None:
        # 画面の配信が、API のルートの判定（405）を横取りしない
        response = client.get("/api/imports", headers={"X-VidCut-Token": TOKEN})
        assert response.status_code == 405
        assert response.json()["success"] is False

    def test_unknown_api_path_is_not_answered_with_the_page(self, client: TestClient) -> None:
        response = client.get("/api/nope", headers={"X-VidCut-Token": TOKEN})
        assert response.status_code == 404
        assert response.json()["success"] is False
        assert client.get("/api").status_code == 404

    def test_page_is_served_under_a_root_path_too(self, tmp_path: Path, dist: Path) -> None:
        client = make_client(tmp_path, dist)
        prefixed = TestClient(client.app, base_url=BASE_URL, root_path="/x")
        assert TOKEN_TAG in prefixed.get("/x/lectures/abc").text
        assert prefixed.get("/x/api/nope", headers={"X-VidCut-Token": TOKEN}).status_code == 404

    def test_only_get_is_answered_with_the_page(self, client: TestClient) -> None:
        for method in ("HEAD", "POST"):
            response = client.request(method, "/")
            assert response.status_code in (404, 405)
            assert TOKEN not in response.text
            assert response.headers["x-content-type-options"] == "nosniff"

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

    def test_path_the_file_system_cannot_handle_is_not_found(self, client: TestClient) -> None:
        assert client.get("/assets/a%00b.js").status_code == 404
        response = client.get("/lectures/a%00b")  # 画面のパスとしては、画面の HTML を返す
        assert response.status_code == 200
        assert TOKEN_TAG in response.text

    @pytest.mark.parametrize("path", ["/assets/missing.js", "/favicon.ico", "/a/b/c.css.map"])
    def test_missing_file_is_not_answered_with_the_page(
        self, client: TestClient, path: str
    ) -> None:
        # ファイルを求めた要求に HTML を返すと、画面が壊れた理由が分かりにくい
        response = client.get(path)
        assert response.status_code == 404
        assert TOKEN not in response.text

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
        # API は frontend がなくても使える
        assert client.get("/api/lectures", headers={"X-VidCut-Token": TOKEN}).status_code == 200

    def test_build_guide_carries_the_token_for_the_dev_server(self, tmp_path: Path) -> None:
        # 開発中は Vite のプラグインが、このページからトークンを読む（ADR-006）
        response = make_client(tmp_path, None).get("/")
        assert response.text.count(TOKEN_TAG) == 1
        assert response.text.index(TOKEN_TAG) < response.text.index("</head>")
        assert response.headers["cache-control"] == "no-store"

    def test_build_guide_is_not_served_to_another_host(self, tmp_path: Path) -> None:
        response = make_client(tmp_path, None).get("/", headers={"Host": "evil.example"})
        assert response.status_code == 403
        assert TOKEN not in response.text

    def test_page_without_a_head_is_replaced_by_the_build_guide(
        self, tmp_path: Path, dist: Path
    ) -> None:
        (dist / "index.html").write_text("<html><body></body></html>", encoding="utf-8")
        response = make_client(tmp_path, dist).get("/")
        assert response.status_code == 503
        assert "npm" in response.text
        assert response.text.count(TOKEN_TAG) == 1


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
        assert "object-src 'none'" in policy  # <object> や <embed> で何も読み込ませない
        assert "script-src" not in policy or "'unsafe-inline'" not in policy.split("script-src")[1]

    def test_inline_styles_are_not_allowed_except_the_waveform_style(
        self, client: TestClient
    ) -> None:
        policy = client.get("/").headers["content-security-policy"]
        directives = dict(part.split(" ", 1) for part in policy.split("; "))
        # インラインは、スクリプトもスタイルも許可しない（style 属性も不可）。
        # 例外は、波形の部品（wavesurfer.js）が差し込む style 要素 1 つだけ（ハッシュで許可）
        assert "'unsafe-inline'" not in policy
        assert "style-src-attr" not in directives
        assert "style-src-elem" not in directives
        sources = directives["style-src"].split(" ")
        assert sources[0] == "'self'"
        assert len(sources) == 2
        assert re.fullmatch(r"'sha256-[A-Za-z0-9+/]{43}='", sources[1])

    def test_waveform_style_hash_is_the_one_the_frontend_test_checks(
        self, client: TestClient
    ) -> None:
        # frontend のテスト（waveChart.test.ts）は、wavesurfer.js が実際に差し込む style 要素の
        # ハッシュが、このファイルの値と同じことを確かめる。CSP も同じ値を許可していること
        shared = json.loads(WAVEFORM_STYLE_HASH_FILE.read_text(encoding="utf-8"))
        policy = client.get("/").headers["content-security-policy"]
        assert shared["hash"] == WAVEFORM_STYLE_HASH
        assert f"style-src 'self' '{shared['hash']}'" in policy.split("; ")

    def test_images_and_media_come_only_from_the_app_itself(self, client: TestClient) -> None:
        # 画面は data: も blob: も使わない（proxy 動画は自分自身の URL、波形は canvas に描く）
        policy = client.get("/").headers["content-security-policy"]
        directives = dict(part.split(" ", 1) for part in policy.split("; "))
        assert directives["img-src"] == "'self'"
        assert directives["media-src"] == "'self'"
        assert "data:" not in policy
        assert "blob:" not in policy

    def test_startup_and_shutdown_pass_through(self, tmp_path: Path, dist: Path) -> None:
        with make_client(tmp_path, dist) as client:
            assert client.get("/").status_code == 200

    def test_refusals_by_the_guard_carry_the_headers_too(self, client: TestClient) -> None:
        response = client.get("/", headers={"Host": "evil.example:8765"})
        assert response.headers["x-content-type-options"] == "nosniff"

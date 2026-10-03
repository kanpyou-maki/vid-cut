import logging

import pytest

from tests.api.conftest import ApiEnv
from vidcut.api.envelope import ErrorOut
from vidcut.api.messages import ERROR_MESSAGES
from vidcut.domain.models import ErrorCode


class TestErrors:
    def test_unknown_path_and_method_use_the_envelope(self, env: ApiEnv) -> None:
        env.error(404, "GET", "/api/nope")
        env.error(405, "DELETE", "/api/lectures")

    def test_invalid_json_is_refused(self, env: ApiEnv) -> None:
        env.error(
            422,
            "POST",
            "/api/imports",
            content=b"{not json",
            headers={"Content-Type": "application/json"},
        )

    def test_validation_error_does_not_echo_the_input(self, env: ApiEnv) -> None:
        message = env.error(422, "POST", "/api/imports", json={"paths": "/secret/input/value"})
        assert "/secret/input/value" not in message

    def test_unexpected_error_is_logged_but_not_shown(
        self, env: ApiEnv, caplog: pytest.LogCaptureFixture
    ) -> None:
        (env.workspace / "vidcut.sqlite3").write_bytes(b"not a database")
        with caplog.at_level(logging.ERROR):
            message = env.error(500, "GET", "/api/lectures")
        assert "ログ" in message
        assert "database" not in message
        assert "not a database" in caplog.text

    def test_no_interactive_docs_are_served(self, env: ApiEnv) -> None:
        # 画面の JS を外部の CDN から読むページを、ローカルアプリには置かない。
        # これらのパスは、ほかの知らないパスと同じ扱い（画面の HTML。ここではビルドがないので 503）
        for path in ("/docs", "/redoc", "/openapi.json"):
            response = env.client.get(path)
            assert response.status_code == 503
            assert "swagger" not in response.text.lower()
            assert '"openapi"' not in response.text


class TestOpenApi:
    """frontend の型は OpenAPI から作る（M6 の PR 3）。スキーマが実際の応答と合っていること。"""

    def test_failures_are_described_as_the_envelope(self, env: ApiEnv) -> None:
        schema = env.app.openapi()
        assert "HTTPValidationError" not in schema["components"]["schemas"]
        operations = [op for path in schema["paths"].values() for op in path.values()]
        assert len(operations) == 14
        for operation in operations:
            for status in ("401", "403", "404", "422", "500"):
                content = operation["responses"][status]["content"]["application/json"]
                assert content["schema"] == {"$ref": "#/components/schemas/ErrorOut"}
        error = schema["components"]["schemas"]["ErrorOut"]
        assert set(error["required"]) == {"success", "data", "error"}

    def test_conflict_is_described_where_it_can_happen(self, env: ApiEnv) -> None:
        schema = env.app.openapi()
        edits = schema["paths"]["/api/lectures/{lecture_id}/edits"]["put"]
        assert "409" in edits["responses"]

    def test_proxy_is_described_as_a_video(self, env: ApiEnv) -> None:
        schema = env.app.openapi()
        proxy = schema["paths"]["/api/recordings/{recording_id}/proxy"]["get"]
        assert list(proxy["responses"]["200"]["content"]) == ["video/mp4"]
        assert "206" in proxy["responses"]

    def test_error_response_matches_the_described_shape(self, env: ApiEnv) -> None:
        body = env.client.get("/api/lectures/nope").json()
        assert ErrorOut.model_validate(body).error == body["error"]


class TestGuardIsInstalled:
    def test_requests_without_the_token_are_refused(self, env: ApiEnv) -> None:
        response = env.client.get("/api/lectures", headers={"X-VidCut-Token": ""})
        assert response.status_code == 401

    def test_requests_from_another_host_are_refused(self, env: ApiEnv) -> None:
        response = env.client.get("/api/lectures", headers={"Host": "evil.example:8765"})
        assert response.status_code == 403


def test_every_error_code_has_a_message() -> None:
    assert set(ERROR_MESSAGES) == set(ErrorCode)
    assert all(message for message in ERROR_MESSAGES.values())

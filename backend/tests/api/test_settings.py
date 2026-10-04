from pathlib import Path
from typing import Any

import pytest

from tests.api.conftest import ApiEnv, build_env
from vidcut.api.security import TOKEN_HEADER
from vidcut.pipeline.export import ExportSettings

DEFAULT = {"before_ms": 150, "after_ms": 250, "after_sentence_ms": 500}
CHOSEN = {"before_ms": 100, "after_ms": 300, "after_sentence_ms": 800}


class TestGetSettings:
    def test_starts_with_the_defaults(self, env: ApiEnv) -> None:
        assert env.data("GET", "/api/settings") == {
            "keep_padding": DEFAULT,
            "default_keep_padding": DEFAULT,
            "customized": False,
        }

    def test_defaults_follow_the_export_settings(self, tmp_path: Path) -> None:
        settings = ExportSettings(pad_before_ms=40, pad_after_ms=900, pad_after_sentence_ms=1_200)
        env = build_env(tmp_path, export_settings=settings)
        assert env.data("GET", "/api/settings")["default_keep_padding"] == {
            "before_ms": 40,
            "after_ms": 900,
            "after_sentence_ms": 1_200,
        }


class TestPutSettings:
    def test_saves_the_padding(self, env: ApiEnv) -> None:
        saved = env.data("PUT", "/api/settings", json={"keep_padding": CHOSEN})

        assert saved == {
            "keep_padding": CHOSEN,
            "default_keep_padding": DEFAULT,
            "customized": True,
        }
        assert env.data("GET", "/api/settings") == saved

    def test_lecture_detail_tells_the_saved_padding(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("a.mov")
        env.data("PUT", "/api/settings", json={"keep_padding": CHOSEN})

        assert env.data("GET", f"/api/lectures/{lecture['id']}")["keep_padding"] == CHOSEN

    def test_null_returns_to_the_defaults(self, env: ApiEnv) -> None:
        env.data("PUT", "/api/settings", json={"keep_padding": CHOSEN})

        reset = env.data("PUT", "/api/settings", json={"keep_padding": None})

        assert reset == {
            "keep_padding": DEFAULT,
            "default_keep_padding": DEFAULT,
            "customized": False,
        }

    def test_accepts_the_bounds(self, env: ApiEnv) -> None:
        bounds = {"before_ms": 0, "after_ms": 2_000, "after_sentence_ms": 0}
        assert env.data("PUT", "/api/settings", json={"keep_padding": bounds})["keep_padding"] == (
            bounds
        )

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"keep_padding": {**CHOSEN, "before_ms": -1}},
            {"keep_padding": {**CHOSEN, "after_ms": 2_001}},
            {"keep_padding": {**CHOSEN, "after_sentence_ms": 1.5}},
            {"keep_padding": {**CHOSEN, "after_sentence_ms": "800"}},
            {"keep_padding": {**CHOSEN, "after_sentence_ms": True}},
            {"keep_padding": {"before_ms": 100, "after_ms": 300}},
            {"keep_padding": {**CHOSEN, "extra": 1}},
            {"keep_padding": CHOSEN, "fps": 30},
            {"keep_padding": [100, 300, 800]},
        ],
    )
    def test_rejects_values_outside_the_form(self, env: ApiEnv, body: dict[str, Any]) -> None:
        env.error(422, "PUT", "/api/settings", json=body)
        assert env.data("GET", "/api/settings")["customized"] is False

    def test_requires_the_token(self, env: ApiEnv) -> None:
        response = env.client.put(
            "/api/settings", json={"keep_padding": CHOSEN}, headers={TOKEN_HEADER: "wrong"}
        )
        assert response.status_code == 401


class TestExportUsesTheSettings:
    def test_export_after_a_change_keeps_the_new_padding(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("a.mov")
        url = f"/api/lectures/{lecture['id']}/exports"

        env.data("POST", url, json={"format": "premiere_xml"})
        env.run_worker()
        before = _exported_xml(env, lecture["title"])
        tight = {"before_ms": 0, "after_ms": 0, "after_sentence_ms": 0}
        env.data("PUT", "/api/settings", json={"keep_padding": tight})
        env.data("POST", url, json={"format": "premiere_xml"})
        env.run_worker()

        after = _exported_xml(env, lecture["title"])
        assert "<in>" in before and after != before


def _exported_xml(env: ApiEnv, title: str) -> str:
    return (env.workspace / "exports" / title / f"{title}.xml").read_text(encoding="utf-8")

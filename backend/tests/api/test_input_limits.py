"""入力の上限の境界: ちょうど上限は通り、1 つ超えるとスキーマで断られる（Design Doc 3-5）。

スキーマで断られた要求の文は INVALID_REQUEST。services が断るとき（録画ファイルの長さを超える、
など）は別の文になるので、どちらで断られたかを文で見分ける。
"""

from typing import Any

import pytest

from tests.api.conftest import ApiEnv
from vidcut.api.inputs import (
    MAX_IMPORT_PATHS,
    MAX_LECTURE_RECORDINGS,
    MAX_MANUAL_CUTS,
    MAX_PATH_CHARS,
    MAX_RESTORED_SUGGESTIONS,
    MAX_SUGGESTION_ID_CHARS,
    MAX_TIME_MS,
)
from vidcut.api.messages import INVALID_REQUEST
from vidcut.domain.titles import MAX_TITLE_CHARS

MAX_ID_CHARS = 64


def refused_by_schema(env: ApiEnv, method: str, url: str, **kwargs: Any) -> None:
    assert env.error(422, method, url, **kwargs) == INVALID_REQUEST


class TestPaths:
    def path_of_length(self, env: ApiEnv, length: int) -> str:
        """ホーム配下の、ちょうど length 文字のパス（1 要素は 100 文字まで。実在はしない）。"""
        path = str(env.home.resolve())
        while len(path) < length:
            path += "/" + "a" * min(100, length - len(path) - 1)
        assert len(path) == length
        return path

    def test_path_at_the_limit_reaches_the_file_system(self, env: ApiEnv) -> None:
        path = self.path_of_length(env, MAX_PATH_CHARS)
        response = env.client.get("/api/fs", params={"path": path})
        assert response.json()["error"] != INVALID_REQUEST  # 見つからない、または扱えないパス

    def test_path_over_the_limit(self, env: ApiEnv) -> None:
        path = self.path_of_length(env, MAX_PATH_CHARS + 1)
        refused_by_schema(env, "GET", "/api/fs", params={"path": path})
        refused_by_schema(env, "POST", "/api/imports", json={"paths": [path]})

    def test_empty_path(self, env: ApiEnv) -> None:
        refused_by_schema(env, "GET", "/api/fs", params={"path": ""})
        refused_by_schema(env, "POST", "/api/imports", json={"paths": [""]})

    def test_number_of_import_paths(self, env: ApiEnv) -> None:
        video = str(env.video("a.mov"))
        refused_by_schema(
            env, "POST", "/api/imports", json={"paths": [video] * (MAX_IMPORT_PATHS + 1)}
        )
        data = env.data("POST", "/api/imports", json={"paths": [video] * MAX_IMPORT_PATHS})
        assert (len(data["added"]), len(data["existing"])) == (1, MAX_IMPORT_PATHS - 1)


class TestIds:
    def test_id_at_the_limit_is_looked_up(self, env: ApiEnv) -> None:
        env.error(404, "GET", "/api/lectures/" + "a" * MAX_ID_CHARS)

    def test_id_over_the_limit(self, env: ApiEnv) -> None:
        refused_by_schema(env, "GET", "/api/lectures/" + "a" * (MAX_ID_CHARS + 1))


class TestMergeAndOrder:
    def test_number_of_lectures_to_merge(self, env: ApiEnv) -> None:
        def ids(count: int) -> list[str]:
            return [f"unknown{i}" for i in range(count)]

        env.error(404, "POST", "/api/lectures/merge", json={"lecture_ids": ids(50)})
        assert MAX_LECTURE_RECORDINGS == 50
        refused_by_schema(env, "POST", "/api/lectures/merge", json={"lecture_ids": ids(51)})

    def test_title_length(self, env: ApiEnv) -> None:
        first, second = env.imported("a.mov", "b.mov")
        pair = [first["id"], second["id"]]
        refused_by_schema(
            env,
            "POST",
            "/api/lectures/merge",
            json={"lecture_ids": pair, "title": "あ" * (MAX_TITLE_CHARS + 1)},
        )
        merged = env.data(
            "POST",
            "/api/lectures/merge",
            json={"lecture_ids": pair, "title": "あ" * MAX_TITLE_CHARS},
        )
        assert merged["title"] == "あ" * MAX_TITLE_CHARS

    def test_number_of_recordings_to_order(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("a.mov")
        url = f"/api/lectures/{lecture['id']}/order"

        def ids(count: int) -> list[str]:
            return [f"r{i}" for i in range(count)]

        # 上限ちょうどはスキーマを通り、services が構成の違いで断る
        message = env.error(422, "PUT", url, json={"recording_ids": ids(MAX_LECTURE_RECORDINGS)})
        assert "構成" in message
        refused_by_schema(env, "PUT", url, json={"recording_ids": ids(MAX_LECTURE_RECORDINGS + 1)})
        refused_by_schema(env, "PUT", url, json={"recording_ids": []})


class TestEdits:
    @pytest.fixture
    def target(self, env: ApiEnv) -> tuple[str, str]:
        """編集の保存先の URL と、録画ファイル（10 秒）の id。"""
        (lecture,) = env.imported("a.mov")
        return f"/api/lectures/{lecture['id']}/edits", lecture["recordings"][0]["id"]

    def body(self, **changes: Any) -> dict[str, Any]:
        return {"version": 0, "restored_suggestion_ids": [], "manual_cuts": [], **changes}

    def cut(self, recording_id: str, index: int, start: int, end: int) -> dict[str, Any]:
        return {"id": f"m{index}", "recording_id": recording_id, "start_ms": start, "end_ms": end}

    def test_shortest_cut_is_one_millisecond(self, env: ApiEnv, target: tuple[str, str]) -> None:
        url, rid = target
        saved = env.data("PUT", url, json=self.body(manual_cuts=[self.cut(rid, 0, 0, 1)]))
        assert saved["version"] == 1

    def test_time_at_the_limit_is_checked_against_the_recording(
        self, env: ApiEnv, target: tuple[str, str]
    ) -> None:
        url, rid = target
        body = self.body(manual_cuts=[self.cut(rid, 0, 0, MAX_TIME_MS)])
        assert "長さ" in env.error(422, "PUT", url, json=body)

    def test_time_over_the_limit(self, env: ApiEnv, target: tuple[str, str]) -> None:
        url, rid = target
        body = self.body(manual_cuts=[self.cut(rid, 0, 0, MAX_TIME_MS + 1)])
        refused_by_schema(env, "PUT", url, json=body)

    def test_number_of_manual_cuts(self, env: ApiEnv, target: tuple[str, str]) -> None:
        url, rid = target

        def cuts(count: int) -> list[dict[str, Any]]:
            return [self.cut(rid, i, i, i + 1) for i in range(count)]

        refused_by_schema(env, "PUT", url, json=self.body(manual_cuts=cuts(MAX_MANUAL_CUTS + 1)))
        saved = env.data("PUT", url, json=self.body(manual_cuts=cuts(MAX_MANUAL_CUTS)))
        assert len(saved["manual_cuts"]) == MAX_MANUAL_CUTS

    def test_number_of_restored_suggestions(self, env: ApiEnv, target: tuple[str, str]) -> None:
        url, _ = target

        def restored(count: int) -> list[str]:
            return [f"s{i}" for i in range(count)]

        over = self.body(restored_suggestion_ids=restored(MAX_RESTORED_SUGGESTIONS + 1))
        refused_by_schema(env, "PUT", url, json=over)
        at_limit = self.body(restored_suggestion_ids=restored(MAX_RESTORED_SUGGESTIONS))
        saved = env.data("PUT", url, json=at_limit)
        assert len(saved["restored_suggestion_ids"]) == MAX_RESTORED_SUGGESTIONS

    def test_length_of_a_suggestion_id(self, env: ApiEnv, target: tuple[str, str]) -> None:
        url, _ = target
        for bad in ("x" * (MAX_SUGGESTION_ID_CHARS + 1), ""):
            refused_by_schema(env, "PUT", url, json=self.body(restored_suggestion_ids=[bad]))
        at_limit = self.body(restored_suggestion_ids=["x" * MAX_SUGGESTION_ID_CHARS])
        assert env.data("PUT", url, json=at_limit)["version"] == 1

    def test_length_of_a_cut_id(self, env: ApiEnv, target: tuple[str, str]) -> None:
        url, rid = target
        cut = self.cut(rid, 0, 0, 1)
        over = self.body(manual_cuts=[{**cut, "id": "m" * (MAX_ID_CHARS + 1)}])
        refused_by_schema(env, "PUT", url, json=over)
        at_limit = self.body(manual_cuts=[{**cut, "id": "m" * MAX_ID_CHARS}])
        assert env.data("PUT", url, json=at_limit)["version"] == 1

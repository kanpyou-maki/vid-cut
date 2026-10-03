from typing import Any

import pytest

from tests.api.conftest import ApiEnv
from tests.pipeline.judge_fakes import delete_output

RETAKE = delete_output({"id": 0, "kind": "retake", "reason": "<b>言い直し</b>", "superseded_by": 1})


def ids(lectures: list[dict[str, Any]]) -> list[str]:
    return [lecture["id"] for lecture in lectures]


class TestList:
    def test_shows_status_recordings_and_latest_jobs(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("S05-12.mov")
        assert (lecture["title"], lecture["status"]) == ("S05-12", "ready")
        (recording,) = lecture["recordings"]
        assert (recording["name"], recording["duration_ms"]) == ("S05-12.mov", 10_000)
        assert (recording["width"], recording["height"]) == (1920, 1080)
        assert [(j["kind"], j["status"]) for j in lecture["jobs"]] == [
            ("analyze_recording", "succeeded"),
            ("judge_lecture", "succeeded"),
        ]

    def test_empty(self, env: ApiEnv) -> None:
        assert env.data("GET", "/api/lectures") == []


class TestDetail:
    def test_returns_everything_the_editor_needs(self, env: ApiEnv) -> None:
        video = str(env.video("S05-12.mov"))
        env.data("POST", "/api/imports", json={"paths": [video]})
        env.run_worker(RETAKE)
        (lecture,) = env.data("GET", "/api/lectures")
        detail = env.data("GET", f"/api/lectures/{lecture['id']}")
        assert (detail["id"], detail["title"], detail["status"]) == (
            lecture["id"],
            "S05-12",
            "ready",
        )
        (recording,) = detail["recordings"]
        assert (recording["analyzed"], recording["analysis_unreadable"]) == (True, False)
        assert "".join(t["text"] for t in recording["tokens"]) == "えーとこんにちは"
        token = recording["tokens"][0]
        assert set(token) == {
            "id",
            "chunk_id",
            "text",
            "start_ms",
            "end_ms",
            "asr_confidence",
            "align_score",
        }
        assert [c["id"] for c in recording["chunks"]] == sorted(
            {t["chunk_id"] for t in recording["tokens"]}
        )
        assert {s["kind"] for s in recording["suggestions"]} <= {"silence", "filler"}
        assert recording["silences"][0] == {"start_ms": 0, "end_ms": 1_000}
        assert {m["kind"] for m in recording["review_marks"]} <= {
            "low_confidence",
            "unrecognized_speech",
        }
        assert detail["judged"] is True
        (judged,) = detail["judged_suggestions"]
        # 言語モデルの文字列は、そのまま返す（エスケープは画面の役目。Design Doc 3-5-2）
        assert (judged["kind"], judged["reason"]) == ("retake", "<b>言い直し</b>")
        assert judged["recording_id"] == recording["id"]
        assert detail["dropped_restored_ids"] == []
        assert detail["edit_state"] == {
            "version": 0,
            "restored_suggestion_ids": [],
            "manual_cuts": [],
        }

    def test_before_analysis_there_is_nothing_to_edit_yet(self, env: ApiEnv) -> None:
        env.data("POST", "/api/imports", json={"paths": [str(env.video("a.mov"))]})
        (lecture,) = env.data("GET", "/api/lectures")
        detail = env.data("GET", f"/api/lectures/{lecture['id']}")
        (recording,) = detail["recordings"]
        assert (detail["status"], detail["judged"]) == ("queued", False)
        assert (recording["analyzed"], recording["tokens"]) == (False, [])

    def test_unreadable_analysis_is_flagged(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("a.mov")
        recording_id = lecture["recordings"][0]["id"]
        (env.workspace / "recordings" / recording_id / "analysis.json").write_text("{}")
        (recording,) = env.data("GET", f"/api/lectures/{lecture['id']}")["recordings"]
        assert (recording["analyzed"], recording["analysis_unreadable"]) == (False, True)

    def test_unknown_lecture(self, env: ApiEnv) -> None:
        env.error(404, "GET", "/api/lectures/" + "0" * 32)

    @pytest.mark.parametrize("bad", ["a b", "x" * 65, "a.b", "あ"])
    def test_ids_with_unexpected_characters_are_refused(self, env: ApiEnv, bad: str) -> None:
        env.error(422, "GET", f"/api/lectures/{bad}")


class TestMergeOrderSplit:
    def test_merge_then_reorder_then_split(self, env: ApiEnv) -> None:
        first, second = env.imported("S05-12.mov", "S05-12-retake.mov")
        merged = env.data(
            "POST",
            "/api/lectures/merge",
            json={"lecture_ids": [second["id"], first["id"]], "title": " まとめ\n講座 "},
        )
        assert merged["title"] == "まとめ 講座"
        recording_ids = [second["recordings"][0]["id"], first["recordings"][0]["id"]]
        assert merged["recording_ids"] == recording_ids
        (listed,) = env.data("GET", "/api/lectures")
        assert (listed["id"], listed["status"]) == (merged["id"], "queued")  # 判定が積まれた

        reordered = env.data(
            "PUT",
            f"/api/lectures/{merged['id']}/order",
            json={"recording_ids": recording_ids[::-1]},
        )
        assert reordered["recording_ids"] == recording_ids[::-1]

        parts = env.data("POST", f"/api/lectures/{merged['id']}/split")
        assert [p["title"] for p in parts] == ["S05-12", "S05-12-retake"]
        assert ids(env.data("GET", "/api/lectures")) == ids(parts)

    def test_merge_without_a_title_uses_the_first_lecture(self, env: ApiEnv) -> None:
        first, second = env.imported("a.mov", "b.mov")
        merged = env.data(
            "POST", "/api/lectures/merge", json={"lecture_ids": [first["id"], second["id"]]}
        )
        assert merged["title"] == "a"

    def test_merge_input_limits(self, env: ApiEnv) -> None:
        first, second = env.imported("a.mov", "b.mov")
        pair = [first["id"], second["id"]]
        for body in (
            {"lecture_ids": [first["id"]]},
            {"lecture_ids": pair, "title": "あ" * 101},
            {"lecture_ids": pair, "title": 1},
            {"lecture_ids": pair, "title": "​"},
            {"lecture_ids": [first["id"], first["id"]]},
            {"lecture_ids": [*pair, "x" * 65]},
            {"lecture_ids": ["id"] * 51},
            {"lecture_ids": pair, "extra": True},
        ):
            env.error(422, "POST", "/api/lectures/merge", json=body)
        assert len(env.data("GET", "/api/lectures")) == 2

    def test_merge_with_an_unknown_lecture(self, env: ApiEnv) -> None:
        (first,) = env.imported("a.mov")
        env.error(404, "POST", "/api/lectures/merge", json={"lecture_ids": [first["id"], "nope"]})

    def test_order_must_keep_the_same_recordings(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("a.mov")
        message = env.error(
            422, "PUT", f"/api/lectures/{lecture['id']}/order", json={"recording_ids": ["other"]}
        )
        assert "構成" in message

    def test_split_of_a_single_recording_lecture(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("a.mov")
        assert "まとめた" in env.error(422, "POST", f"/api/lectures/{lecture['id']}/split")

    def test_unknown_lecture(self, env: ApiEnv) -> None:
        env.error(404, "PUT", "/api/lectures/nope/order", json={"recording_ids": ["r"]})
        env.error(404, "POST", "/api/lectures/nope/split")
        env.error(404, "POST", "/api/lectures/nope/reanalyze")


class TestReanalyze:
    def test_enqueues_an_analysis_of_each_recording(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("a.mov")
        jobs = env.data("POST", f"/api/lectures/{lecture['id']}/reanalyze")
        assert [(j["kind"], j["target_id"], j["status"]) for j in jobs] == [
            ("analyze_recording", lecture["recordings"][0]["id"], "queued")
        ]
        (listed,) = env.data("GET", "/api/lectures")
        assert listed["status"] == "queued"


class TestEdits:
    def cut(self, recording_id: str, start: int = 100, end: int = 200) -> dict[str, Any]:
        return {"id": "m1", "recording_id": recording_id, "start_ms": start, "end_ms": end}

    def test_saves_and_returns_the_next_version(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("a.mov")
        rid = lecture["recordings"][0]["id"]
        url = f"/api/lectures/{lecture['id']}/edits"
        body = {"version": 0, "restored_suggestion_ids": ["s1"], "manual_cuts": [self.cut(rid)]}
        saved = env.data("PUT", url, json=body)
        assert saved == {**body, "version": 1}
        assert env.data("GET", f"/api/lectures/{lecture['id']}")["edit_state"] == saved

    def test_stale_version_is_a_conflict(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("a.mov")
        url = f"/api/lectures/{lecture['id']}/edits"
        body = {"version": 0, "restored_suggestion_ids": [], "manual_cuts": []}
        env.data("PUT", url, json=body)
        assert "読み込み直して" in env.error(409, "PUT", url, json=body)

    def test_cut_outside_the_lecture_or_the_recording_is_refused(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("a.mov")
        rid = lecture["recordings"][0]["id"]
        url = f"/api/lectures/{lecture['id']}/edits"
        for cut in (self.cut("other"), self.cut(rid, 9_000, 10_001)):
            body = {"version": 0, "restored_suggestion_ids": [], "manual_cuts": [cut]}
            env.error(422, "PUT", url, json=body)

    def test_input_limits(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("a.mov")
        rid = lecture["recordings"][0]["id"]
        url = f"/api/lectures/{lecture['id']}/edits"
        base: dict[str, Any] = {"version": 0, "restored_suggestion_ids": [], "manual_cuts": []}
        day = 24 * 60 * 60 * 1000
        for change in (
            {"version": "0"},
            {"version": 0.0},
            {"version": True},
            {"version": -1},
            {"manual_cuts": [self.cut(rid, 200, 100)]},
            {"manual_cuts": [self.cut(rid, 100, 100)]},
            {"manual_cuts": [self.cut(rid, -1, 100)]},
            {"manual_cuts": [self.cut(rid, 0, day + 1)]},
            {"manual_cuts": [self.cut(rid, 0.5, 100)]},  # type: ignore[arg-type]
            {"manual_cuts": [{**self.cut(rid), "id": "x" * 65}]},
            {"manual_cuts": [{**self.cut(rid), "extra": 1}]},
            {"manual_cuts": [{**self.cut(rid), "id": f"m{i}"} for i in range(2001)]},
            {"restored_suggestion_ids": ["s"] * 20001},
            {"restored_suggestion_ids": ["x" * 101]},
            {"restored_suggestion_ids": [1]},
        ):
            env.error(422, "PUT", url, json={**base, **change})
        assert env.data("GET", f"/api/lectures/{lecture['id']}")["edit_state"]["version"] == 0

    def test_unknown_lecture(self, env: ApiEnv) -> None:
        body = {"version": 0, "restored_suggestion_ids": [], "manual_cuts": []}
        env.error(404, "PUT", "/api/lectures/nope/edits", json=body)


class TestExports:
    @pytest.mark.parametrize(
        ("export_format", "kind"), [("premiere_xml", "export_premiere"), ("mp4", "export_mp4")]
    )
    def test_enqueues_an_export_job(self, env: ApiEnv, export_format: str, kind: str) -> None:
        (lecture,) = env.imported("S05-12.mov")
        url = f"/api/lectures/{lecture['id']}/exports"
        job = env.data("POST", url, json={"format": export_format})
        assert (job["kind"], job["target_id"], job["status"]) == (kind, lecture["id"], "queued")
        assert env.data("POST", url, json={"format": export_format})["id"] == job["id"]
        env.run_worker()
        names = [p.name for p in (env.workspace / "exports" / "S05-12").iterdir()]
        assert names == ["S05-12.xml" if export_format == "premiere_xml" else "S05-12.mp4"]

    def test_unknown_format_or_lecture(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("a.mov")
        env.error(422, "POST", f"/api/lectures/{lecture['id']}/exports", json={"format": "gif"})
        env.error(422, "POST", f"/api/lectures/{lecture['id']}/exports", json={})
        env.error(404, "POST", "/api/lectures/nope/exports", json={"format": "mp4"})

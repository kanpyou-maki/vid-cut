from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tests.api.conftest import ApiEnv, build_env
from tests.pipeline.judge_fakes import delete_output
from vidcut.adapters.sqlite.judgements import SqliteJudgementRepository
from vidcut.pipeline.export import ExportSettings
from vidcut.pipeline.ports import Judgement, RevealFailedError

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

    def test_tells_the_padding_that_the_export_keeps_around_speech(self, env: ApiEnv) -> None:
        """プレビューが、書き出しと同じ区間を残せるようにする（余白の値を画面に持たせない）。"""
        (lecture,) = env.imported("a.mov")
        detail = env.data("GET", f"/api/lectures/{lecture['id']}")
        assert detail["keep_padding"] == {"before_ms": 150, "after_ms": 250}

    def test_padding_follows_the_export_settings(self, tmp_path: Path) -> None:
        settings = ExportSettings(pad_before_ms=40, pad_after_ms=900)
        env = build_env(tmp_path, export_settings=settings)
        (lecture,) = env.imported("a.mov")
        detail = env.data("GET", f"/api/lectures/{lecture['id']}")
        assert detail["keep_padding"] == {"before_ms": 40, "after_ms": 900}

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
        analysis = env.workspace / "recordings" / recording_id / "analysis.json"
        analysis.write_text('{"CORRUPT-MARKER": 1}')
        response = env.client.get(f"/api/lectures/{lecture['id']}")
        (recording,) = response.json()["data"]["recordings"]
        assert (recording["analyzed"], recording["analysis_unreadable"]) == (False, True)
        assert "CORRUPT-MARKER" not in response.text  # 読めなかった中身は応答に出さない

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


class TestDroppedRestorations:
    def url(self, lecture_id: str) -> str:
        return f"/api/lectures/{lecture_id}/dropped-restorations/dismiss"

    def drop(self, env: ApiEnv, lecture_id: str, *ids: str) -> None:
        """判定のやり直しで、戻した候補を引き継げなかった状態にする。"""
        with env.api.services() as services:
            judgements = SqliteJudgementRepository(services.conn)
            judgements.save(Judgement(lecture_id, "k", (), dropped_restored_ids=ids))

    def test_removes_the_shown_ids_and_returns_the_rest(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("a.mov")
        self.drop(env, lecture["id"], "a", "b", "c")
        remaining = env.data("POST", self.url(lecture["id"]), json={"ids": ["a", "c"]})
        assert remaining == {"dropped_restored_ids": ["b"]}
        detail = env.data("GET", f"/api/lectures/{lecture['id']}")
        assert detail["dropped_restored_ids"] == ["b"]

    def test_ids_that_are_not_recorded_are_ignored(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("a.mov")
        self.drop(env, lecture["id"], "a")
        remaining = env.data("POST", self.url(lecture["id"]), json={"ids": ["zzz"]})
        assert remaining == {"dropped_restored_ids": ["a"]}

    def test_input_limits(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("a.mov")
        self.drop(env, lecture["id"], "a")
        for body in (
            {},
            {"ids": []},
            {"ids": "a"},
            {"ids": [1]},
            {"ids": [""]},
            {"ids": ["x" * 101]},
            {"ids": ["s"] * 20001},
            {"ids": ["a"], "extra": 1},
        ):
            env.error(422, "POST", self.url(lecture["id"]), json=body)
        detail = env.data("GET", f"/api/lectures/{lecture['id']}")
        assert detail["dropped_restored_ids"] == ["a"]

    def test_unknown_lecture(self, env: ApiEnv) -> None:
        env.error(404, "POST", self.url("nope"), json={"ids": ["a"]})


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


class TestExportStatus:
    """書き出しの状態と保存先（Design Doc 3-5）。詳細にも、軽い API にも同じものが出る。"""

    def url(self, lecture_id: str) -> str:
        return f"/api/lectures/{lecture_id}/exports"

    def test_detail_tells_where_the_exports_go(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("S05-12.mov")
        directory = env.workspace / "exports" / "S05-12"
        never = {"exported_at": None, "job": None}
        assert env.data("GET", f"/api/lectures/{lecture['id']}")["exports"] == {
            "directory": str(directory),
            "shared_with_other_lectures": False,
            "premiere_xml": {"path": str(directory / "S05-12.xml"), **never},
            "mp4": {"path": str(directory / "S05-12.mp4"), **never},
        }
        assert not (env.workspace / "exports").exists()  # 読むだけで、フォルダは作らない

    def test_status_follows_the_job_and_then_the_file(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("S05-12.mov")
        job = env.data("POST", self.url(lecture["id"]), json={"format": "premiere_xml"})
        waiting = env.data("GET", self.url(lecture["id"]))
        assert waiting["premiere_xml"]["job"] == job
        assert (job["status"], waiting["premiere_xml"]["exported_at"]) == ("queued", None)
        assert waiting["mp4"] == {"path": waiting["mp4"]["path"], "exported_at": None, "job": None}

        env.run_worker()
        done = env.data("GET", self.url(lecture["id"]))
        assert done["premiere_xml"]["job"]["status"] == "succeeded"
        exported = env.workspace / "exports" / "S05-12" / "S05-12.xml"
        assert datetime.fromisoformat(
            done["premiere_xml"]["exported_at"]
        ) == datetime.fromtimestamp(exported.stat().st_mtime, tz=UTC)
        assert env.data("GET", f"/api/lectures/{lecture['id']}")["exports"] == done

    def test_failed_export_shows_the_kind_and_a_fixed_sentence(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("a.mov")
        rid = lecture["recordings"][0]["id"]
        everything = {"id": "m1", "recording_id": rid, "start_ms": 0, "end_ms": 10_000}
        env.data(
            "PUT",
            f"/api/lectures/{lecture['id']}/edits",
            json={"version": 0, "restored_suggestion_ids": [], "manual_cuts": [everything]},
        )
        env.data("POST", self.url(lecture["id"]), json={"format": "mp4"})
        env.run_worker()
        response = env.client.get(self.url(lecture["id"]))
        job = response.json()["data"]["mp4"]["job"]
        assert (job["status"], job["error_code"]) == ("failed", "nothing_to_export")
        assert job["error_message"] == "残す区間がありません（すべて削除されています）"
        assert response.json()["data"]["mp4"]["exported_at"] is None

    def test_tells_when_another_lecture_has_the_same_name(self, env: ApiEnv) -> None:
        first, second = env.imported("a.mov", "retake/a.mov")
        assert (first["title"], second["title"]) == ("a", "a")
        for lecture in (first, second):
            assert env.data("GET", self.url(lecture["id"]))["shared_with_other_lectures"] is True

    def test_unknown_lecture_or_unexpected_id(self, env: ApiEnv) -> None:
        env.error(404, "GET", self.url("nope"))
        env.error(422, "GET", self.url("a.b"))


class TestRevealExports:
    """Finder で開く（Design Doc 3-5・3-5-1）。開く場所はレクチャーの id から求める。"""

    def url(self, lecture_id: str) -> str:
        return f"/api/lectures/{lecture_id}/exports/reveal"

    def exported(self, env: ApiEnv, export_format: str = "premiere_xml") -> dict[str, Any]:
        (lecture,) = env.imported("S05-12.mov")
        env.data("POST", f"/api/lectures/{lecture['id']}/exports", json={"format": export_format})
        env.run_worker()
        return lecture

    def test_selects_the_exported_file(self, env: ApiEnv) -> None:
        lecture = self.exported(env)
        assert env.data("POST", self.url(lecture["id"])) == {"target": "file"}
        exported = (env.workspace / "exports" / "S05-12" / "S05-12.xml").resolve()
        assert env.revealer.revealed == [exported]

    def test_a_path_in_the_request_is_not_used(self, env: ApiEnv) -> None:
        lecture = self.exported(env)
        env.data("POST", self.url(lecture["id"]), json={"path": "/etc/passwd", "target": "/etc"})
        (revealed,) = env.revealer.revealed
        assert revealed.is_relative_to((env.workspace / "exports").resolve())

    def test_nothing_was_exported_yet(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("a.mov")
        assert "まだありません" in env.error(422, "POST", self.url(lecture["id"]))
        assert env.revealer.revealed == []
        assert not (env.workspace / "exports").exists()

    def test_symlinked_destination_is_refused_without_telling_the_path(self, env: ApiEnv) -> None:
        (lecture,) = env.imported("a.mov")
        outside = env.home / "outside"
        outside.mkdir()
        (env.workspace / "exports").mkdir()
        (env.workspace / "exports" / "a").symlink_to(outside, target_is_directory=True)
        message = env.error(422, "POST", self.url(lecture["id"]))
        assert "シンボリックリンク" in message
        assert str(env.home) not in message
        assert env.revealer.revealed == []

    def test_failure_of_finder_is_a_fixed_sentence(self, env: ApiEnv) -> None:
        lecture = self.exported(env)
        env.revealer.error = RevealFailedError(f"open: {env.workspace}/exports: 生のエラー文")
        response = env.client.post(self.url(lecture["id"]))
        assert response.status_code == 500
        assert response.json() == {
            "success": False,
            "data": None,
            "error": "Finder で開けませんでした。"
            "詳しくは vidcut serve を起動したターミナルのログを確認してください",
        }
        assert str(env.workspace) not in response.text
        assert "content-security-policy" in response.headers

    def test_unknown_lecture(self, env: ApiEnv) -> None:
        env.error(404, "POST", self.url("nope"))
        assert env.revealer.revealed == []

    def test_requires_the_token(self, env: ApiEnv) -> None:
        lecture = self.exported(env)
        response = env.client.post(self.url(lecture["id"]), headers={"X-VidCut-Token": "wrong"})
        assert response.status_code == 401
        assert env.revealer.revealed == []

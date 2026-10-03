from pathlib import Path

from tests.api.conftest import ApiEnv, build_env
from tests.pipeline.fakes import FakeMediaTool
from vidcut.pipeline.ports import ExternalToolError, ProbeResult


class TestImports:
    def test_registers_recordings_and_enqueues_analysis(self, env: ApiEnv) -> None:
        video = env.video("S05-12.mov")
        data = env.data("POST", "/api/imports", json={"paths": [str(video)]})
        (added,) = data["added"]
        assert (added["name"], added["source_path"]) == ("S05-12.mov", str(video))
        assert added["duration_ms"] == 10_000
        assert (data["existing"], data["failed"]) == ([], [])
        (lecture,) = env.data("GET", "/api/lectures")
        assert (lecture["title"], lecture["status"]) == ("S05-12", "queued")
        jobs = env.data("GET", "/api/jobs")
        assert [(j["kind"], j["target_id"]) for j in jobs] == [
            ("analyze_recording", added["id"]),
            ("make_mezzanine", added["id"]),
        ]

    def test_folder_imports_its_videos_and_same_file_is_not_registered_twice(
        self, env: ApiEnv
    ) -> None:
        first = env.video("a.mov")
        env.video("b.mp4")
        env.data("POST", "/api/imports", json={"paths": [str(first)]})
        data = env.data("POST", "/api/imports", json={"paths": [str(first.parent)]})
        assert [r["name"] for r in data["added"]] == ["b.mp4"]
        assert [r["name"] for r in data["existing"]] == ["a.mov"]

    def test_missing_file_is_reported_without_stopping_the_others(self, env: ApiEnv) -> None:
        video = env.video("a.mov")
        missing = str(video.parent / "nope.mov")
        data = env.data("POST", "/api/imports", json={"paths": [missing, str(video)]})
        assert [r["name"] for r in data["added"]] == ["a.mov"]
        assert data["failed"] == [
            {"path": missing, "code": "source_missing", "message": data["failed"][0]["message"]}
        ]
        assert "見つかりません" in data["failed"][0]["message"]

    def test_failure_reports_the_code_but_not_the_raw_error(self, tmp_path: Path) -> None:
        class BrokenProbe(FakeMediaTool):
            def probe(self, source: Path) -> ProbeResult:
                raise ExternalToolError(f"ffprobe が失敗しました: {source} stderr: secret detail")

        env = build_env(tmp_path, BrokenProbe())
        video = env.video("a.mov")
        response = env.client.post("/api/imports", json={"paths": [str(video)]})
        (failure,) = response.json()["data"]["failed"]
        assert failure["code"] == "tool_failed"
        assert "secret detail" not in response.text

    def test_paths_outside_home_or_hidden_refuse_the_whole_request(self, env: ApiEnv) -> None:
        video = env.video("a.mov")
        (env.home / ".ssh").mkdir()
        for bad in ("/etc/hosts", str(env.home / ".ssh"), "relative/a.mov"):
            env.error(422, "POST", "/api/imports", json={"paths": [str(video), bad]})
        assert env.data("GET", "/api/lectures") == []

    def test_symlink_to_a_video_outside_home_is_refused(self, env: ApiEnv, tmp_path: Path) -> None:
        outside = tmp_path / "outside.mov"
        outside.write_bytes(b"x")
        link = env.video("a.mov").parent / "link.mov"
        link.symlink_to(outside)
        env.error(422, "POST", "/api/imports", json={"paths": [str(link)]})

    def test_input_limits(self, env: ApiEnv) -> None:
        video = str(env.video("a.mov"))
        for body in (
            {},
            {"paths": []},
            {"paths": [video] * 201},
            {"paths": ["/" + "a" * 5000]},
            {"paths": [video], "extra": 1},
            {"paths": video},
            {"paths": [1]},
        ):
            env.error(422, "POST", "/api/imports", json=body)

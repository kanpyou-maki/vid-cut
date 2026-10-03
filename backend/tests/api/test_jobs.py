from pathlib import Path
from types import SimpleNamespace

from tests.api.conftest import ApiEnv, build_env
from tests.pipeline.fakes import FakeMediaTool
from vidcut.api.deps import get_services
from vidcut.pipeline.ports import ExternalToolError


class FailingAudio(FakeMediaTool):
    """音声の取り出しが、絶対パスと ffmpeg の出力を含むエラーで失敗する。"""

    def extract_audio(self, source: Path, dest: Path) -> None:
        raise ExternalToolError(f"ffmpeg が失敗しました: {source}: secret stderr")


class TestJobs:
    def test_lists_jobs_with_progress(self, env: ApiEnv) -> None:
        env.imported("a.mov")
        jobs = env.data("GET", "/api/jobs")
        assert [(j["kind"], j["status"], j["progress"]) for j in jobs] == [
            ("analyze_recording", "succeeded", 1.0),
            ("make_mezzanine", "succeeded", 1.0),
            ("judge_lecture", "succeeded", 1.0),
        ]
        assert set(jobs[0]) == {
            "id",
            "kind",
            "target_id",
            "status",
            "stage",
            "progress",
            "error_code",
            "error_message",
            "created_at",
            "updated_at",
        }
        assert (jobs[0]["error_code"], jobs[0]["error_message"]) == (None, None)

    def test_failed_job_shows_a_code_and_a_fixed_message_only(self, tmp_path: Path) -> None:
        env = build_env(tmp_path, FailingAudio())
        env.data("POST", "/api/imports", json={"paths": [str(env.video("a.mov"))]})
        env.run_worker()
        jobs_response = env.client.get("/api/jobs")
        lectures_response = env.client.get("/api/lectures")
        failed = jobs_response.json()["data"][0]
        assert (failed["status"], failed["error_code"]) == ("failed", "tool_failed")
        assert "ffmpeg" in failed["error_message"]
        (lecture,) = lectures_response.json()["data"]
        assert lecture["status"] == "failed"
        assert lecture["jobs"][0]["error_code"] == "tool_failed"
        for response in (jobs_response, lectures_response):
            assert "secret stderr" not in response.text
            assert str(tmp_path) not in response.text.replace(
                lecture["recordings"][0]["source_path"], ""
            )

    def test_retry_puts_a_failed_job_back_in_the_queue(self, tmp_path: Path) -> None:
        env = build_env(tmp_path, FailingAudio())
        env.data("POST", "/api/imports", json={"paths": [str(env.video("a.mov"))]})
        env.run_worker()
        failed = env.data("GET", "/api/jobs")[0]
        retried = env.data("POST", f"/api/jobs/{failed['id']}/retry")
        assert (retried["id"], retried["status"]) == (failed["id"], "queued")
        assert (retried["error_code"], retried["error_message"]) == (None, None)

    def test_only_failed_jobs_can_be_retried(self, env: ApiEnv) -> None:
        env.imported("a.mov")
        done = env.data("GET", "/api/jobs")[0]
        assert "失敗したジョブ" in env.error(422, "POST", f"/api/jobs/{done['id']}/retry")

    def test_unknown_job(self, env: ApiEnv) -> None:
        env.error(404, "POST", "/api/jobs/nope/retry")

    def test_job_that_disappears_during_the_retry(self, env: ApiEnv) -> None:
        class VanishingQueue:
            def retry(self, job_id: str) -> None:
                pass

            def get(self, job_id: str) -> None:
                return None

        app = env.client.app
        app.dependency_overrides[get_services] = lambda: SimpleNamespace(queue=VanishingQueue())  # type: ignore[attr-defined]
        env.error(404, "POST", "/api/jobs/gone/retry")

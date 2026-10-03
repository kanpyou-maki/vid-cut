import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.pipeline.fakes import FakeAligner, FakeMediaTool, FakeTranscriber, FakeVad
from vidcut.bootstrap import App, MlTools, build_app
from vidcut.cli import main
from vidcut.domain.models import Job, JobKind, JobStatus


def fake_build(workspace: Path) -> Callable[[], App]:
    def build() -> App:
        return build_app(
            workspace,
            media=FakeMediaTool(),
            ml=MlTools(vad=FakeVad(), transcriber=FakeTranscriber(), aligner=FakeAligner()),
        )

    return build


@pytest.fixture
def video(tmp_path: Path) -> Path:
    path = tmp_path / "S05-12.mov"
    path.write_bytes(b"mov")
    return path


def statuses(workspace: Path) -> list[JobStatus]:
    app = fake_build(workspace)()
    try:
        return [stored.job.status for stored in app.queue.list_all()]
    finally:
        app.close()


class TestAnalyze:
    def test_enqueues_without_processing(
        self, tmp_path: Path, video: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["analyze", str(video)], build=fake_build(tmp_path / "ws"))
        out = capsys.readouterr().out
        assert code == 0
        assert "登録: 1 本" in out
        assert "vidcut worker" in out
        assert statuses(tmp_path / "ws") == [JobStatus.QUEUED, JobStatus.QUEUED]

    def test_wait_processes_all_jobs(
        self, tmp_path: Path, video: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["analyze", str(video), "--wait"], build=fake_build(tmp_path / "ws"))
        out = capsys.readouterr().out
        assert code == 0
        assert "成功: 2 件" in out
        assert statuses(tmp_path / "ws") == [JobStatus.SUCCEEDED, JobStatus.SUCCEEDED]

    def test_failed_import_returns_error_code(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["analyze", str(tmp_path / "missing.mov")], build=fake_build(tmp_path / "ws"))
        assert code == 1
        assert "missing.mov" in capsys.readouterr().out

    def test_failed_job_returns_error_code(
        self, tmp_path: Path, video: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["analyze", str(video)], build=fake_build(tmp_path / "ws"))
        video.unlink()  # 解析の前に元の録画ファイルが消えた
        code = main(
            ["analyze", str(tmp_path / "other.mov"), "--wait"], build=fake_build(tmp_path / "ws")
        )
        out = capsys.readouterr().out
        assert code == 1
        assert "失敗: 2 件" in out


class TestWorker:
    def test_recovers_interrupted_jobs_then_stops(self, tmp_path: Path) -> None:
        build = fake_build(tmp_path / "ws")
        app = build()
        app.queue.enqueue(Job(id="j1", kind=JobKind.ANALYZE_RECORDING, target_id="r"))
        app.queue.claim_next()
        app.close()
        stop = threading.Event()
        stop.set()
        assert main(["worker"], build=build, stop=stop) == 0
        assert statuses(tmp_path / "ws") == [JobStatus.QUEUED]


def test_requires_a_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 2

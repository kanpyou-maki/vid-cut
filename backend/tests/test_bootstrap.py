import xml.etree.ElementTree as ET
from pathlib import Path

from tests.pipeline.fakes import FakeAligner, FakeMediaTool, FakeTranscriber, FakeVad
from tests.pipeline.judge_fakes import FakeModel
from vidcut.bootstrap import (
    MlTools,
    build_app,
    judge_workdir,
    media_settings_for,
    workspace_from_env,
)
from vidcut.domain.models import JobKind, JobStatus
from vidcut.pipeline.export import ExportSettings


def test_workspace_defaults_to_home_vidcut() -> None:
    assert workspace_from_env({}) == Path.home() / "VidCut"


def test_workspace_from_environment_variable(tmp_path: Path) -> None:
    assert workspace_from_env({"VIDCUT_WORKSPACE": str(tmp_path / "ws")}) == tmp_path / "ws"


def test_workspace_expands_home() -> None:
    assert workspace_from_env({"VIDCUT_WORKSPACE": "~/x"}) == Path.home() / "x"


def test_build_app_creates_database_and_worker(tmp_path: Path) -> None:
    app = build_app(tmp_path / "ws")
    try:
        assert (tmp_path / "ws" / "vidcut.sqlite3").exists()
        assert set(app.handlers) == set(JobKind)
        assert app.worker().run_once() is None
    finally:
        app.close()


def test_judge_runs_claude_in_neutral_directory_inside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    assert judge_workdir(workspace) == workspace / "judge"
    assert not judge_workdir(workspace).is_relative_to(Path(__file__).parents[2])


def test_exports_use_the_frame_rate_of_the_mezzanine(tmp_path: Path) -> None:
    # 中間素材と書き出しのフレームレートが食い違うと、カット点がずれる
    settings = ExportSettings(fps=30)
    assert media_settings_for(settings).mezzanine_fps == 30
    assert media_settings_for(ExportSettings()).mezzanine_fps == 60


def test_export_requested_before_the_mezzanine_job_ran_makes_the_mezzanine_itself(
    tmp_path: Path,
) -> None:
    # 書き出しは中間素材のジョブより優先度が高い。中間素材を待たずに失敗する、ということがないこと
    video = tmp_path / "S05-12.mov"
    video.write_bytes(b"mov")
    media = FakeMediaTool()
    app = build_app(
        tmp_path / "ws",
        media=media,
        ml=MlTools(vad=FakeVad(), transcriber=FakeTranscriber(), aligner=FakeAligner()),
        model=FakeModel(['{"delete": []}']),
    )
    try:
        app.imports.import_paths([video])
        (lecture,) = app.lectures.list_all()
        worker = app.worker()
        analyzed = worker.run_once()
        assert analyzed is not None and analyzed.kind is JobKind.ANALYZE_RECORDING
        app.exports.request(lecture.id, JobKind.EXPORT_PREMIERE)
        app.exports.request(lecture.id, JobKind.EXPORT_MP4)
        processed = []
        while (job := worker.run_once()) is not None:
            processed.append(job.kind)
        jobs = [stored.job for stored in app.queue.list_all()]
    finally:
        app.close()
    assert processed == [
        JobKind.JUDGE_LECTURE,
        JobKind.EXPORT_PREMIERE,
        JobKind.EXPORT_MP4,
        JobKind.MAKE_MEZZANINE,
    ]
    assert [job.status for job in jobs] == [JobStatus.SUCCEEDED] * 5
    assert media.calls["make_mezzanine"] == 1
    exports = tmp_path / "ws" / "exports" / "S05-12"
    assert sorted(p.name for p in exports.iterdir()) == ["S05-12.mp4", "S05-12.xml"]
    mezzanine = tmp_path / "ws" / "recordings" / lecture.recording_ids[0] / "mezzanine.mp4"
    pathurl = ET.parse(exports / "S05-12.xml").getroot().findtext(".//pathurl")
    assert pathurl == f"file://localhost{mezzanine}"

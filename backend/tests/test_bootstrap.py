import sqlite3
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.pipeline.fakes import FakeAligner, FakeMediaTool, FakeTranscriber, FakeVad
from tests.pipeline.judge_fakes import FakeModel
from vidcut.adapters.finder import FinderRevealer, LoggingRevealer
from vidcut.bootstrap import (
    DATABASE_FILE,
    MlTools,
    build_api,
    build_app,
    judge_workdir,
    media_settings_for,
    revealer_from_env,
    workspace_from_env,
)
from vidcut.domain.intervals import Interval
from vidcut.domain.models import JobKind, JobStatus, ManualCut
from vidcut.pipeline.export import ExportSettings
from vidcut.services.lecture_views import LectureStatus


def test_workspace_defaults_to_home_vidcut() -> None:
    assert workspace_from_env({}) == Path.home() / "VidCut"


def test_workspace_from_environment_variable(tmp_path: Path) -> None:
    assert workspace_from_env({"VIDCUT_WORKSPACE": str(tmp_path / "ws")}) == tmp_path / "ws"


def test_workspace_expands_home() -> None:
    assert workspace_from_env({"VIDCUT_WORKSPACE": "~/x"}) == Path.home() / "x"


def test_reveal_opens_finder_unless_it_is_turned_off() -> None:
    assert isinstance(revealer_from_env({}), FinderRevealer)
    # 自動の確認と E2E では、Finder を開かずにログへ出すだけにする
    assert isinstance(revealer_from_env({"VIDCUT_REVEAL": "off"}), LoggingRevealer)


@pytest.mark.parametrize("value", ["", "on", "OFF", "/bin/sh", "0"])
def test_reveal_setting_cannot_be_anything_but_off(value: str) -> None:
    """止めることしかできない（別のコマンドに差し替える口にしない）。"""
    with pytest.raises(ValueError, match="VIDCUT_REVEAL"):
        revealer_from_env({"VIDCUT_REVEAL": value})


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


def test_merged_lecture_is_judged_edited_and_split_through_the_wired_services(
    tmp_path: Path,
) -> None:
    # M6 の API が使う services（まとめる・編集の保存・一覧と詳細）が、同じ DB でつながること
    videos = [tmp_path / "S05-12.mov", tmp_path / "S05-12-retake.mov"]
    for index, video in enumerate(videos):
        video.write_bytes(b"mov" * (index + 1))
    app = build_app(
        tmp_path / "ws",
        media=FakeMediaTool(),
        ml=MlTools(vad=FakeVad(), transcriber=FakeTranscriber(), aligner=FakeAligner()),
        model=FakeModel(['{"delete": []}'] * 5),
    )
    try:
        app.imports.import_paths(videos)
        app.worker().run_until_idle()
        first, second = app.lectures.list_all()

        merged = app.lecture_service.merge([first.id, second.id], title="S05-12 まとめ")
        waiting = app.lecture_views.summaries()
        app.worker().run_until_idle()
        detail = app.lecture_views.detail(merged.id)

        cut = ManualCut(id="m1", recording_id=second.recording_ids[0], span=Interval(100, 200))
        saved = app.edits.save(detail.edit_state.add_manual_cut(cut))
        parts = app.lecture_service.split(merged.id)
        split_cuts = [app.lecture_views.detail(part.id).edit_state.manual_cuts for part in parts]
        reanalysis = app.lecture_service.reanalyze(parts[0].id)
    finally:
        app.close()
    assert [summary.status for summary in waiting] == [LectureStatus.QUEUED]
    assert detail.summary.status is LectureStatus.READY
    assert list(detail.analyses) == [first.recording_ids[0], second.recording_ids[0]]
    assert detail.judgement is not None
    assert saved.version == 1
    assert [part.title for part in parts] == ["S05-12", "S05-12-retake"]
    assert split_cuts == [(), (cut,)]
    assert [job.kind for job in reanalysis] == [JobKind.ANALYZE_RECORDING]


class TestBuildApi:
    def test_each_scope_opens_its_own_connection_and_closes_it(self, tmp_path: Path) -> None:
        api = build_api(tmp_path / "ws", media=FakeMediaTool())
        with api.services() as first, api.services() as second:
            assert first.conn is not second.conn
            assert first.lecture_views.summaries() == ()
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            first.conn.execute("SELECT 1")

    def test_scope_can_be_used_from_another_thread(self, tmp_path: Path) -> None:
        # FastAPI は依存の準備と本体を別のスレッドで動かすことがある（Design Doc 3-5-2）
        api = build_api(tmp_path / "ws", media=FakeMediaTool())
        with api.services() as services, ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(services.lecture_views.summaries).result() == ()

    def test_work_requested_through_the_api_is_done_by_the_worker(self, tmp_path: Path) -> None:
        video = tmp_path / "S05-12.mov"
        video.write_bytes(b"mov")
        media = FakeMediaTool()
        api = build_api(tmp_path / "ws", media=media)
        with api.services() as services:
            (recording,) = services.imports.import_paths([video]).added
            (summary,) = services.lecture_views.summaries()
        app = build_app(
            tmp_path / "ws",
            media=media,
            ml=MlTools(vad=FakeVad(), transcriber=FakeTranscriber(), aligner=FakeAligner()),
            model=FakeModel(['{"delete": []}']),
        )
        try:
            app.worker().run_until_idle()
        finally:
            app.close()
        with api.services() as services:
            detail = services.lecture_views.detail(summary.lecture.id)
            export = services.exports.request(summary.lecture.id, JobKind.EXPORT_PREMIERE)
            merged_judgement = services.lecture_service.reanalyze(summary.lecture.id)
        assert summary.status is LectureStatus.QUEUED
        assert detail.summary.status is LectureStatus.READY
        assert list(detail.analyses) == [recording.id]
        assert detail.judgement is not None
        assert export.kind is JobKind.EXPORT_PREMIERE
        assert [job.target_id for job in merged_judgement] == [recording.id]

    def test_schema_is_prepared_once_when_the_api_is_built(self, tmp_path: Path) -> None:
        api = build_api(tmp_path / "ws", media=FakeMediaTool())
        (tmp_path / "ws" / DATABASE_FILE).unlink()
        # リクエストごとの接続はスキーマを作らない（起動時に 1 回だけ移行する）
        with api.services() as services, pytest.raises(sqlite3.OperationalError, match="no such"):
            services.lecture_views.summaries()

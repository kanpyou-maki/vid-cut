import os
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.pipeline.fakes import FakeRevealer, make_recording
from vidcut.adapters.sqlite.database import open_database
from vidcut.adapters.sqlite.jobs import SqliteJobQueue
from vidcut.adapters.sqlite.lectures import SqliteLectureRepository
from vidcut.adapters.sqlite.recordings import SqliteRecordingRepository
from vidcut.adapters.workspace import FileExportStore
from vidcut.domain.models import ErrorCode, Job, JobKind, JobStatus, Lecture
from vidcut.pipeline.ports import InvalidInputError, NotFoundError, RevealFailedError
from vidcut.services.export_destinations import ExportDestinations, RevealTarget

TITLE = "S05-12"


@dataclass
class Env:
    workspace: Path
    lectures: SqliteLectureRepository
    queue: SqliteJobQueue
    store: FileExportStore
    revealer: FakeRevealer
    service: ExportDestinations

    @property
    def directory(self) -> Path:
        return self.workspace / "exports" / TITLE

    def exported(self, suffix: str, at: int) -> Path:
        """書き出し済みのファイルを置く。at は更新日時（エポック秒）。"""
        path = self.store.write_text(TITLE, suffix, "x")
        os.utime(path, (at, at))
        return path

    def job(self, job_id: str, kind: JobKind, target_id: str = "l1") -> Job:
        job = Job(id=job_id, kind=kind, target_id=target_id)
        self.queue.enqueue(job)
        return job


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    conn: sqlite3.Connection = open_database(tmp_path / "db.sqlite3")
    recordings = SqliteRecordingRepository(conn)
    for rid in ("r1", "r2"):
        source = tmp_path / f"{rid}.mov"
        source.write_bytes(rid.encode())
        recordings.add(make_recording(source, rid))
    lectures = SqliteLectureRepository(conn)
    lectures.save(Lecture(id="l1", title=TITLE, recording_ids=("r1",)))
    queue = SqliteJobQueue(conn)
    # 解決済みのパスと比べられるよう、ワークスペースは実体のパスにしておく
    workspace = tmp_path.resolve() / "ws"
    store = FileExportStore(workspace)
    revealer = FakeRevealer()
    service = ExportDestinations(lectures=lectures, queue=queue, exports=store, revealer=revealer)
    yield Env(workspace, lectures, queue, store, revealer, service)
    conn.close()


class TestStatus:
    def test_tells_where_each_format_goes_before_anything_was_exported(self, env: Env) -> None:
        status = env.service.status("l1")
        assert status.directory == env.directory
        assert status.shared_with_other_lectures is False
        assert (status.premiere.file.path, status.mp4.file.path) == (
            env.directory / f"{TITLE}.xml",
            env.directory / f"{TITLE}.mp4",
        )
        assert (status.premiere.file.exported_at, status.mp4.file.exported_at) == (None, None)
        assert (status.premiere.job, status.mp4.job) == (None, None)
        assert not (env.workspace / "exports").exists()  # 読むだけで、フォルダは作らない

    def test_tells_when_each_format_was_last_exported(self, env: Env) -> None:
        env.exported(".mp4", 1_800_000_000)
        status = env.service.status("l1")
        assert status.premiere.file.exported_at is None
        assert status.mp4.file.exported_at == datetime.fromtimestamp(1_800_000_000, tz=UTC)

    def test_shows_the_latest_export_job_of_each_format(self, env: Env) -> None:
        env.job("old", JobKind.EXPORT_MP4)
        env.job("new", JobKind.EXPORT_MP4)
        env.job("xml", JobKind.EXPORT_PREMIERE)
        env.job("judge", JobKind.JUDGE_LECTURE)
        env.job("other", JobKind.EXPORT_MP4, target_id="l2")
        status = env.service.status("l1")
        assert status.premiere.job is not None and status.mp4.job is not None
        assert (status.premiere.job.id, status.mp4.job.id) == ("xml", "new")
        assert status.mp4.job.status is JobStatus.QUEUED

    def test_failed_job_carries_the_kind_of_failure_but_not_the_raw_text(self, env: Env) -> None:
        env.job("j1", JobKind.EXPORT_MP4)
        env.queue.claim_next()
        env.queue.mark_failed("j1", "/Users/me/secret: 生のエラー文", ErrorCode.NOTHING_TO_EXPORT)
        job = env.service.status("l1").mp4.job
        assert job is not None
        assert (job.status, job.error_code) == (JobStatus.FAILED, ErrorCode.NOTHING_TO_EXPORT)
        assert not hasattr(job, "error")

    @pytest.mark.parametrize(
        ("other_title", "shared"),
        [
            (TITLE, True),
            ("s05-12", True),  # 大文字と小文字を区別しないボリュームでは、同じフォルダになる
            ("S05-12 ", True),  # ファイル名に直すと同じ名前になる
            ("S05-13", False),
        ],
    )
    def test_tells_when_another_lecture_exports_to_the_same_place(
        self, env: Env, other_title: str, shared: bool
    ) -> None:
        env.lectures.save(Lecture(id="l2", title=other_title, recording_ids=("r2",)))
        assert env.service.status("l1").shared_with_other_lectures is shared

    def test_unknown_lecture(self, env: Env) -> None:
        with pytest.raises(NotFoundError):
            env.service.status("missing")


class TestReveal:
    def test_selects_the_newest_exported_file(self, env: Env) -> None:
        env.exported(".xml", 1_800_000_000)
        mp4 = env.exported(".mp4", 1_800_000_500)
        assert env.service.reveal("l1") is RevealTarget.FILE
        assert env.revealer.revealed == [mp4]

        xml = env.exported(".xml", 1_800_001_000)
        env.service.reveal("l1")
        assert env.revealer.revealed == [mp4, xml]

    def test_the_path_given_to_the_revealer_is_resolved(self, tmp_path: Path, env: Env) -> None:
        link = tmp_path / "link"
        link.symlink_to(env.workspace.parent, target_is_directory=True)
        store = FileExportStore(link / "ws")  # ワークスペースの手前にリンクがあっても、実体を渡す
        service = ExportDestinations(
            lectures=env.lectures, queue=env.queue, exports=store, revealer=env.revealer
        )
        xml = env.exported(".xml", 1_800_000_000)
        service.reveal("l1")
        assert env.revealer.revealed == [xml]
        assert xml.is_absolute() and xml == xml.resolve()

    def test_selects_the_directory_when_the_files_are_gone(self, env: Env) -> None:
        env.exported(".xml", 1_800_000_000).unlink()
        assert env.service.reveal("l1") is RevealTarget.DIRECTORY
        assert env.revealer.revealed == [env.directory]

    def test_file_that_is_a_symlink_is_not_selected(self, tmp_path: Path, env: Env) -> None:
        outside = tmp_path / "outside.xml"
        outside.write_text("x")
        env.store.path(TITLE, ".xml").symlink_to(outside)
        assert env.service.reveal("l1") is RevealTarget.DIRECTORY
        assert env.revealer.revealed == [env.directory]

    def test_nothing_was_exported_yet(self, env: Env) -> None:
        with pytest.raises(InvalidInputError, match="まだありません"):
            env.service.reveal("l1")
        assert env.revealer.revealed == []
        assert not (env.workspace / "exports").exists()  # 開くためにフォルダを作らない

    def test_refuses_a_symlinked_destination(self, tmp_path: Path, env: Env) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        (env.workspace / "exports").mkdir(parents=True)
        env.directory.symlink_to(outside, target_is_directory=True)
        with pytest.raises(InvalidInputError) as raised:
            env.service.reveal("l1")
        # この文はそのまま画面に出る。パスを入れない
        assert "シンボリックリンク" in str(raised.value)
        assert str(tmp_path) not in str(raised.value)
        assert env.revealer.revealed == []

    def test_failure_to_reveal_is_passed_on(self, env: Env) -> None:
        env.exported(".xml", 1_800_000_000)
        env.revealer.error = RevealFailedError("open が失敗しました")
        with pytest.raises(RevealFailedError):
            env.service.reveal("l1")

    def test_unknown_lecture(self, env: Env) -> None:
        with pytest.raises(NotFoundError):
            env.service.reveal("missing")
        assert env.revealer.revealed == []

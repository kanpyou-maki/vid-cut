import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.pipeline.fakes import FakeMediaTool
from vidcut.adapters.sqlite.database import open_database
from vidcut.adapters.sqlite.jobs import SqliteJobQueue
from vidcut.adapters.sqlite.lectures import SqliteLectureRepository
from vidcut.adapters.sqlite.recordings import SqliteRecordingRepository
from vidcut.domain.models import JobKind
from vidcut.pipeline.ports import ProbeResult, UnsupportedMediaError
from vidcut.services.imports import ImportService


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_database(tmp_path / "db.sqlite3")
    yield connection
    connection.close()


class RejectingMedia(FakeMediaTool):
    def probe(self, source: Path) -> ProbeResult:
        raise UnsupportedMediaError("音声のトラックがありません")


def make_service(conn: sqlite3.Connection, media: FakeMediaTool | None = None) -> ImportService:
    ids = iter(f"id{i}" for i in range(100))
    return ImportService(
        recordings=SqliteRecordingRepository(conn),
        lectures=SqliteLectureRepository(conn),
        queue=SqliteJobQueue(conn),
        media=media or FakeMediaTool(),
        fingerprint=lambda path: f"fp-{path.name}",
        new_id=lambda: next(ids),
    )


def video(directory: Path, name: str) -> Path:
    path = directory / name
    path.write_bytes(b"mov")
    return path


class TestImportPaths:
    def test_registers_recording_lecture_and_jobs(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        result = make_service(conn).import_paths([video(tmp_path, "S05-12.mov")])
        (recording,) = result.added
        assert recording.source_path == str(tmp_path / "S05-12.mov")
        assert recording.duration_ms == 10_000
        lecture = SqliteLectureRepository(conn).find_by_recording(recording.id)
        assert lecture is not None
        assert lecture.title == "S05-12"
        jobs = SqliteJobQueue(conn).list_all()
        assert [(j.job.kind, j.job.target_id) for j in jobs] == [
            (JobKind.ANALYZE_RECORDING, recording.id),
            (JobKind.MAKE_MEZZANINE, recording.id),
        ]

    def test_folder_expands_to_videos_in_name_order(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        folder = tmp_path / "course"
        folder.mkdir()
        for name in ["b.MOV", "a.mp4", "notes.txt", "c.m4v"]:
            video(folder, name)
        (folder / "sub").mkdir()
        result = make_service(conn).import_paths([folder])
        assert [Path(r.source_path).name for r in result.added] == ["a.mp4", "b.MOV", "c.m4v"]

    def test_same_file_is_not_registered_twice(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        service = make_service(conn)
        path = video(tmp_path, "a.mov")
        first = service.import_paths([path])
        second = service.import_paths([path])
        assert second.added == ()
        assert second.existing == first.added
        assert len(SqliteJobQueue(conn).list_all()) == 2

    def test_interrupted_registration_is_completed_on_next_import(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # 前回は録画の登録だけして落ちた（レクチャーもジョブもない）
        path = video(tmp_path, "a.mov")
        service = make_service(conn)
        first = service.import_paths([path]).added[0]
        conn.execute("DELETE FROM jobs")
        conn.execute("DELETE FROM lectures")
        result = service.import_paths([path])
        assert result.added == (first,)
        assert SqliteLectureRepository(conn).find_by_recording(first.id) is not None
        assert len(SqliteJobQueue(conn).list_all()) == 2

    def test_failures_are_reported_and_others_continue(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        missing = tmp_path / "missing.mov"
        result = make_service(conn).import_paths([missing, video(tmp_path, "ok.mov")])
        assert [Path(r.source_path).name for r in result.added] == ["ok.mov"]
        ((path, message),) = result.failed
        assert path == str(missing)
        assert "見つかりません" in message

    def test_unsupported_media_is_reported(self, conn: sqlite3.Connection, tmp_path: Path) -> None:
        result = make_service(conn, RejectingMedia()).import_paths([video(tmp_path, "a.mov")])
        assert result.added == ()
        assert "音声" in result.failed[0][1]
        assert SqliteRecordingRepository(conn).list_all() == ()

    def test_relative_paths_are_resolved(
        self, conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        video(tmp_path, "a.mov")
        monkeypatch.chdir(tmp_path)
        (recording,) = make_service(conn).import_paths([Path("a.mov")]).added
        assert Path(recording.source_path).is_absolute()

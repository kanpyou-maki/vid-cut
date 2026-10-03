import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.pipeline.fakes import (
    DirectoryStore,
    FakeAligner,
    FakeMediaTool,
    FakeTranscriber,
    FakeVad,
    make_recording,
)
from vidcut.adapters.sqlite.database import open_database
from vidcut.adapters.sqlite.recordings import SqliteRecordingRepository
from vidcut.pipeline.analysis import AnalysisSettings, AnalysisTools, load_analysis
from vidcut.pipeline.ports import NotFoundError
from vidcut.services.analysis import AnalysisService


@pytest.fixture
def service(tmp_path: Path) -> Iterator[AnalysisService]:
    conn: sqlite3.Connection = open_database(tmp_path / "db.sqlite3")
    source = tmp_path / "a.mov"
    source.write_bytes(b"mov")
    recordings = SqliteRecordingRepository(conn)
    recordings.add(make_recording(source))
    tools = AnalysisTools(
        media=FakeMediaTool(),
        vad=FakeVad(),
        transcriber=FakeTranscriber(),
        aligner=FakeAligner(),
        store=DirectoryStore(tmp_path / "ws"),
    )
    yield AnalysisService(recordings, tools, AnalysisSettings())
    conn.close()


def test_analyze_saves_result(service: AnalysisService) -> None:
    analysis = service.analyze("r1", lambda s, p: None)
    assert load_analysis(service.store, "r1") == analysis


def test_make_mezzanine(service: AnalysisService) -> None:
    path = service.make_mezzanine("r1", lambda s, p: None)
    assert path.read_bytes() == b"mezzanine"


def test_unknown_recording(service: AnalysisService) -> None:
    with pytest.raises(NotFoundError):
        service.analyze("nope", lambda s, p: None)
    with pytest.raises(NotFoundError):
        service.make_mezzanine("nope", lambda s, p: None)

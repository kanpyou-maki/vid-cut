import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from vidcut.adapters.sqlite.database import open_database
from vidcut.adapters.sqlite.recordings import SqliteRecordingRepository
from vidcut.domain.models import MediaInfo, Recording


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "vidcut.sqlite3"


@pytest.fixture
def conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_database(db_path)
    yield connection
    connection.close()


def make_recording(rid: str = "r1", *, fingerprint: str | None = None) -> Recording:
    return Recording(
        id=rid,
        source_path=f"/Users/me/Movies/{rid}.mov",
        fingerprint=fingerprint or f"fp-{rid}",
        duration_ms=368_977,
        recorded_at=datetime(2026, 9, 10, 14, 26, tzinfo=UTC),
        media=MediaInfo(width=3104, height=1964, is_vfr=True, avg_fps=3.2037, audio_rate=48_000),
    )


@pytest.fixture
def add_recordings(conn: sqlite3.Connection) -> Callable[..., None]:
    repo = SqliteRecordingRepository(conn)

    def add(*ids: str) -> None:
        for rid in ids:
            repo.add(make_recording(rid))

    return add

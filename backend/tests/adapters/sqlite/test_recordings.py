import sqlite3
from dataclasses import replace

import pytest

from tests.adapters.sqlite.conftest import make_recording
from vidcut.adapters.sqlite.recordings import SqliteRecordingRepository


@pytest.fixture
def repo(conn: sqlite3.Connection) -> SqliteRecordingRepository:
    return SqliteRecordingRepository(conn)


class TestSqliteRecordingRepository:
    def test_round_trips_all_fields(self, repo: SqliteRecordingRepository) -> None:
        recording = make_recording("r1")
        repo.add(recording)
        assert repo.get("r1") == recording

    def test_round_trips_missing_recorded_at(self, repo: SqliteRecordingRepository) -> None:
        recording = replace(make_recording("r1"), recorded_at=None)
        repo.add(recording)
        assert repo.get("r1") == recording

    def test_get_unknown_returns_none(self, repo: SqliteRecordingRepository) -> None:
        assert repo.get("nope") is None

    def test_finds_by_fingerprint(self, repo: SqliteRecordingRepository) -> None:
        repo.add(make_recording("r1", fingerprint="abc"))
        found = repo.find_by_fingerprint("abc")
        assert found is not None
        assert found.id == "r1"
        assert repo.find_by_fingerprint("zzz") is None

    def test_rejects_same_file_twice(self, repo: SqliteRecordingRepository) -> None:
        repo.add(make_recording("r1", fingerprint="abc"))
        with pytest.raises(ValueError, match="既に"):
            repo.add(make_recording("r2", fingerprint="abc"))

    def test_rejects_duplicate_id(self, repo: SqliteRecordingRepository) -> None:
        repo.add(make_recording("r1"))
        with pytest.raises(ValueError):
            repo.add(make_recording("r1", fingerprint="other"))

    def test_lists_in_registration_order(self, repo: SqliteRecordingRepository) -> None:
        for rid in ["b", "a", "c"]:
            repo.add(make_recording(rid))
        assert [r.id for r in repo.list_all()] == ["b", "a", "c"]

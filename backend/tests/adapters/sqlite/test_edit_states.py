import sqlite3
from collections.abc import Callable

import pytest

from vidcut.adapters.sqlite.edit_states import SqliteEditStateRepository
from vidcut.adapters.sqlite.lectures import SqliteLectureRepository
from vidcut.domain.intervals import Interval
from vidcut.domain.models import EditState, Lecture, ManualCut
from vidcut.pipeline.ports import NotFoundError, VersionConflictError


@pytest.fixture
def repo(
    conn: sqlite3.Connection, add_recordings: Callable[..., None]
) -> SqliteEditStateRepository:
    add_recordings("r1")
    SqliteLectureRepository(conn).save(Lecture(id="l1", title="t", recording_ids=("r1",)))
    return SqliteEditStateRepository(conn)


def edited(version: int) -> EditState:
    cut = ManualCut(id="m1", recording_id="r1", span=Interval(1_000, 1_500))
    return (
        EditState(lecture_id="l1", version=version).restore("s2").restore("s1").add_manual_cut(cut)
    )


class TestSqliteEditStateRepository:
    def test_unsaved_lecture_starts_empty_at_version_zero(
        self, repo: SqliteEditStateRepository
    ) -> None:
        assert repo.get("l1") == EditState(lecture_id="l1", version=0)

    def test_save_round_trips_and_advances_version(self, repo: SqliteEditStateRepository) -> None:
        saved = repo.save(edited(0))
        assert saved.version == 1
        assert repo.get("l1") == saved
        assert saved.restored_suggestion_ids == frozenset({"s1", "s2"})
        assert saved.manual_cuts == edited(0).manual_cuts

    def test_consecutive_saves_with_latest_version(self, repo: SqliteEditStateRepository) -> None:
        first = repo.save(edited(0))
        second = repo.save(first.unrestore("s1"))
        assert second.version == 2
        assert repo.get("l1").restored_suggestion_ids == frozenset({"s2"})

    def test_stale_version_is_rejected(self, repo: SqliteEditStateRepository) -> None:
        repo.save(edited(0))
        with pytest.raises(VersionConflictError):
            repo.save(edited(0))  # 別のタブが古い版から保存した
        assert repo.get("l1").version == 1

    def test_first_save_must_start_from_version_zero(self, repo: SqliteEditStateRepository) -> None:
        with pytest.raises(VersionConflictError):
            repo.save(edited(3))

    def test_unknown_lecture_cannot_be_saved(self, repo: SqliteEditStateRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.save(EditState(lecture_id="nope", version=0))

    def test_deleting_lecture_removes_its_edits(
        self, conn: sqlite3.Connection, repo: SqliteEditStateRepository
    ) -> None:
        repo.save(edited(0))
        SqliteLectureRepository(conn).delete("l1")
        assert repo.get("l1").version == 0

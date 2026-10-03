import sqlite3
from collections.abc import Callable

import pytest

from vidcut.adapters.sqlite.lectures import SqliteLectureRepository
from vidcut.domain.models import Lecture


@pytest.fixture
def repo(conn: sqlite3.Connection, add_recordings: Callable[..., None]) -> SqliteLectureRepository:
    add_recordings("r1", "r2", "r3")
    return SqliteLectureRepository(conn)


class TestSqliteLectureRepository:
    def test_round_trips_recording_order(self, repo: SqliteLectureRepository) -> None:
        lecture = Lecture(id="l1", title="S05-12", recording_ids=("r3", "r1"))
        repo.save(lecture)
        assert repo.get("l1") == lecture

    def test_get_unknown_returns_none(self, repo: SqliteLectureRepository) -> None:
        assert repo.get("nope") is None

    def test_save_overwrites_title_and_order(self, repo: SqliteLectureRepository) -> None:
        repo.save(Lecture(id="l1", title="old", recording_ids=("r1", "r2")))
        updated = Lecture(id="l1", title="new", recording_ids=("r2", "r1"))
        repo.save(updated)
        assert repo.get("l1") == updated

    def test_finds_lecture_of_recording(self, repo: SqliteLectureRepository) -> None:
        repo.save(Lecture(id="l1", title="t", recording_ids=("r1", "r2")))
        found = repo.find_by_recording("r2")
        assert found is not None
        assert found.id == "l1"
        assert repo.find_by_recording("r3") is None

    def test_recording_belongs_to_at_most_one_lecture(self, repo: SqliteLectureRepository) -> None:
        repo.save(Lecture(id="l1", title="t", recording_ids=("r1",)))
        with pytest.raises(ValueError, match="別のレクチャー"):
            repo.save(Lecture(id="l2", title="t", recording_ids=("r1", "r2")))
        assert repo.get("l2") is None

    def test_rejects_unknown_recording(self, repo: SqliteLectureRepository) -> None:
        with pytest.raises(ValueError):
            repo.save(Lecture(id="l1", title="t", recording_ids=("missing",)))
        assert repo.get("l1") is None

    def test_lists_in_creation_order(self, repo: SqliteLectureRepository) -> None:
        repo.save(Lecture(id="b", title="t", recording_ids=("r1",)))
        repo.save(Lecture(id="a", title="t", recording_ids=("r2",)))
        assert [lecture.id for lecture in repo.list_all()] == ["b", "a"]

    def test_delete_frees_recordings(self, repo: SqliteLectureRepository) -> None:
        repo.save(Lecture(id="l1", title="t", recording_ids=("r1",)))
        repo.delete("l1")
        assert repo.get("l1") is None
        assert repo.find_by_recording("r1") is None

    def test_replace_merges_lectures_atomically(self, repo: SqliteLectureRepository) -> None:
        repo.save(Lecture(id="l1", title="a", recording_ids=("r1",)))
        repo.save(Lecture(id="l2", title="b", recording_ids=("r2",)))
        merged = Lecture(id="l1", title="a", recording_ids=("r1", "r2"))
        repo.replace(remove=["l2"], save=[merged])
        assert repo.list_all() == (merged,)

    def test_replace_splits_lecture(self, repo: SqliteLectureRepository) -> None:
        repo.save(Lecture(id="l1", title="a", recording_ids=("r1", "r2")))
        first = Lecture(id="l1", title="a", recording_ids=("r1",))
        second = Lecture(id="l2", title="a (2)", recording_ids=("r2",))
        repo.replace(remove=[], save=[first, second])
        assert repo.list_all() == (first, second)

    def test_failed_replace_changes_nothing(self, repo: SqliteLectureRepository) -> None:
        original = Lecture(id="l1", title="a", recording_ids=("r1",))
        repo.save(original)
        with pytest.raises(ValueError):
            repo.replace(
                remove=["l1"], save=[Lecture(id="l2", title="b", recording_ids=("missing",))]
            )
        assert repo.list_all() == (original,)

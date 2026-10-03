import sqlite3
from collections.abc import Callable

import pytest

from vidcut.adapters.sqlite.judgements import SqliteJudgementRepository
from vidcut.adapters.sqlite.lectures import SqliteLectureRepository
from vidcut.domain.intervals import Interval
from vidcut.domain.models import CutKind, CutSuggestion, Lecture
from vidcut.pipeline.ports import Judgement, NotFoundError


@pytest.fixture
def repo(
    conn: sqlite3.Connection, add_recordings: Callable[..., None]
) -> SqliteJudgementRepository:
    add_recordings("r1", "r2")
    SqliteLectureRepository(conn).save(Lecture(id="l1", title="t", recording_ids=("r1", "r2")))
    return SqliteJudgementRepository(conn)


def judgement(key: str = "k1") -> Judgement:
    return Judgement(
        lecture_id="l1",
        input_key=key,
        suggestions=(
            CutSuggestion(
                id="r1-c0003-judged",
                recording_id="r1",
                span=Interval(19_223, 23_291),
                kind=CutKind.RETAKE,
                reason="次のファイルで言い直している",
                superseded_by="r2-c0000",
            ),
            CutSuggestion(
                id="r2-c0004-judged",
                recording_id="r2",
                span=Interval(24_673, 25_449),
                kind=CutKind.MISSPEAK,
                reason="途中で途切れている",
            ),
        ),
        dropped_restored_ids=("r1-c0009-judged",),
    )


class TestSqliteJudgementRepository:
    def test_unjudged_lecture_has_no_judgement(self, repo: SqliteJudgementRepository) -> None:
        assert repo.get("l1") is None

    def test_save_round_trips(self, repo: SqliteJudgementRepository) -> None:
        repo.save(judgement())
        assert repo.get("l1") == judgement()

    def test_save_replaces_previous_judgement(self, repo: SqliteJudgementRepository) -> None:
        repo.save(judgement())
        replaced = Judgement(lecture_id="l1", input_key="k2", suggestions=())
        repo.save(replaced)
        assert repo.get("l1") == replaced

    def test_unknown_lecture_cannot_be_saved(self, repo: SqliteJudgementRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.save(Judgement(lecture_id="nope", input_key="k", suggestions=()))

    def test_judgement_is_removed_with_its_lecture(
        self, conn: sqlite3.Connection, repo: SqliteJudgementRepository
    ) -> None:
        repo.save(judgement())
        SqliteLectureRepository(conn).delete("l1")
        assert repo.get("l1") is None

    def test_broken_row_is_reported(
        self, conn: sqlite3.Connection, repo: SqliteJudgementRepository
    ) -> None:
        repo.save(judgement())
        conn.execute("UPDATE judgements SET suggestions = '[{\"id\": 1}]'")
        with pytest.raises(ValueError, match="判定結果"):
            repo.get("l1")

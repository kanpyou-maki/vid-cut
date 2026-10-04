import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.pipeline.fakes import DURATION_MS, NoRecordings, make_recording
from vidcut.adapters.sqlite.database import open_database
from vidcut.adapters.sqlite.edit_states import SqliteEditStateRepository
from vidcut.adapters.sqlite.judgements import SqliteJudgementRepository
from vidcut.adapters.sqlite.lectures import SqliteLectureRepository
from vidcut.adapters.sqlite.recordings import SqliteRecordingRepository
from vidcut.domain.intervals import Interval
from vidcut.domain.models import EditState, Lecture, ManualCut
from vidcut.pipeline.ports import (
    InvalidInputError,
    Judgement,
    NotFoundError,
    VersionConflictError,
)
from vidcut.services.edits import EditService


@dataclass
class Env:
    conn: sqlite3.Connection
    edit_states: SqliteEditStateRepository
    judgements: SqliteJudgementRepository
    service: EditService


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    """レクチャー l1 は録画ファイル r1・r2（各 10 秒）。r3 は別のレクチャー l2 のもの。"""
    conn = open_database(tmp_path / "db.sqlite3")
    recordings = SqliteRecordingRepository(conn)
    for rid in ("r1", "r2", "r3"):
        recordings.add(make_recording(tmp_path / f"{rid}.mov", rid))
    lectures = SqliteLectureRepository(conn)
    lectures.save(Lecture(id="l1", title="S05-12", recording_ids=("r1", "r2")))
    lectures.save(Lecture(id="l2", title="S05-13", recording_ids=("r3",)))
    edit_states = SqliteEditStateRepository(conn)
    judgements = SqliteJudgementRepository(conn)
    service = EditService(
        lectures=lectures, recordings=recordings, edit_states=edit_states, judgements=judgements
    )
    yield Env(conn=conn, edit_states=edit_states, judgements=judgements, service=service)
    conn.close()


def cut(cut_id: str, recording_id: str = "r1", start: int = 100, end: int = 200) -> ManualCut:
    return ManualCut(id=cut_id, recording_id=recording_id, span=Interval(start, end))


def edits(version: int, *cuts: ManualCut, restored: tuple[str, ...] = ()) -> EditState:
    return EditState(
        lecture_id="l1",
        version=version,
        restored_suggestion_ids=frozenset(restored),
        manual_cuts=cuts,
    )


class TestSave:
    def test_saves_and_returns_the_next_version(self, env: Env) -> None:
        state = edits(
            0,
            cut("m1"),
            cut("m2", "r2"),
            cut("m3", start=5_000, end=6_000),
            restored=("r1-silence-0000",),
        )
        saved = env.service.save(state)
        assert saved.version == 1
        assert env.edit_states.get("l1") == saved
        assert saved.manual_cuts == state.manual_cuts
        assert saved.restored_suggestion_ids == {"r1-silence-0000"}

    def test_restoration_of_a_suggestion_that_no_longer_exists_is_accepted(self, env: Env) -> None:
        # 判定のやり直しで候補が消えた直後の画面からも保存できる（削除区間の計算では使われない）
        saved = env.service.save(edits(0, restored=("gone",)))
        assert (saved.version, saved.restored_suggestion_ids) == (1, {"gone"})

    def test_stale_version_is_a_conflict(self, env: Env) -> None:
        env.service.save(edits(0, cut("m1")))
        with pytest.raises(VersionConflictError):
            env.service.save(edits(0, cut("m2")))
        assert env.edit_states.get("l1").manual_cuts == (cut("m1"),)

    def test_cut_may_reach_the_end_of_the_recording(self, env: Env) -> None:
        saved = env.service.save(edits(0, cut("m1", start=0, end=DURATION_MS)))
        assert saved.version == 1

    def test_unknown_lecture(self, env: Env) -> None:
        with pytest.raises(NotFoundError):
            env.service.save(EditState(lecture_id="missing", version=0))

    @pytest.mark.parametrize("recording_id", ["r3", "unknown"])
    def test_cut_must_be_on_a_recording_of_the_lecture(self, env: Env, recording_id: str) -> None:
        with pytest.raises(InvalidInputError, match="録画ファイル"):
            env.service.save(edits(0, cut("m1", recording_id)))
        assert env.edit_states.get("l1").version == 0

    def test_cut_must_end_within_the_recording(self, env: Env) -> None:
        with pytest.raises(InvalidInputError, match="長さ"):
            env.service.save(edits(0, cut("m1", start=9_000, end=DURATION_MS + 1)))

    def test_cut_ids_must_be_unique(self, env: Env) -> None:
        with pytest.raises(InvalidInputError, match="同じ id"):
            env.service.save(edits(0, cut("m1"), cut("m1", "r2")))

    def test_recording_that_is_no_longer_registered(self, env: Env) -> None:
        service = EditService(
            lectures=SqliteLectureRepository(env.conn),
            recordings=NoRecordings(),
            edit_states=env.edit_states,
            judgements=env.judgements,
        )
        with pytest.raises(NotFoundError, match="録画ファイル"):
            service.save(edits(0, cut("m1")))


class TestDismissDroppedRestorations:
    def test_removes_the_shown_ids_and_returns_the_rest(self, env: Env) -> None:
        env.judgements.save(Judgement("l1", "k", (), dropped_restored_ids=("a", "b")))
        assert env.service.dismiss_dropped_restorations("l1", ["a"]) == ("b",)
        judgement = env.judgements.get("l1")
        assert judgement is not None
        assert judgement.dropped_restored_ids == ("b",)

    def test_unjudged_lecture_has_nothing_to_dismiss(self, env: Env) -> None:
        assert env.service.dismiss_dropped_restorations("l1", ["a"]) == ()

    def test_unknown_lecture(self, env: Env) -> None:
        with pytest.raises(NotFoundError):
            env.service.dismiss_dropped_restorations("nope", ["a"])

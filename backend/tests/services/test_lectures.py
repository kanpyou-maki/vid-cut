import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.pipeline.fakes import DirectoryStore, NoRecordings, make_recording
from tests.pipeline.judge_fakes import FakeModel, make_analysis
from vidcut.adapters.sqlite.database import open_database, transaction
from vidcut.adapters.sqlite.edit_states import SqliteEditStateRepository
from vidcut.adapters.sqlite.jobs import SqliteJobQueue
from vidcut.adapters.sqlite.judgements import SqliteJudgementRepository
from vidcut.adapters.sqlite.lectures import SqliteLectureRepository
from vidcut.adapters.sqlite.recordings import SqliteRecordingRepository
from vidcut.domain.intervals import Interval
from vidcut.domain.models import (
    CutKind,
    CutSuggestion,
    EditState,
    Job,
    JobKind,
    JobStatus,
    Lecture,
    ManualCut,
)
from vidcut.domain.titles import FALLBACK_TITLE, MAX_TITLE_CHARS
from vidcut.pipeline.analysis_result import save_analysis
from vidcut.pipeline.judge import JudgeSettings
from vidcut.pipeline.ports import (
    EditStateRepository,
    InvalidInputError,
    Judgement,
    NotFoundError,
    RecordingRepository,
)
from vidcut.services.judge import JudgeService
from vidcut.services.lectures import LectureService


@dataclass
class Env:
    conn: sqlite3.Connection
    store: DirectoryStore
    lectures: SqliteLectureRepository
    edit_states: SqliteEditStateRepository
    judgements: SqliteJudgementRepository
    queue: SqliteJobQueue

    def service(
        self,
        edit_states: EditStateRepository | None = None,
        recordings: RecordingRepository | None = None,
    ) -> LectureService:
        ids = iter(f"new{i}" for i in range(100))

        def new_id() -> str:
            return next(ids)

        judge = JudgeService(
            lectures=self.lectures,
            store=self.store,
            judgements=self.judgements,
            edit_states=self.edit_states,
            atomic=lambda: transaction(self.conn),
            queue=self.queue,
            model=FakeModel([]),
            settings=JudgeSettings(),
            prompt="指示文\n",
            new_id=new_id,
        )
        return LectureService(
            lectures=self.lectures,
            recordings=recordings or SqliteRecordingRepository(self.conn),
            edit_states=edit_states or self.edit_states,
            judgements=self.judgements,
            store=self.store,
            queue=self.queue,
            atomic=lambda: transaction(self.conn),
            request_judge=judge.request_for_recording,
            new_id=new_id,
        )

    def analyzed(self, *recording_ids: str) -> None:
        for rid in recording_ids:
            save_analysis(self.store, make_analysis(rid, ("こんにちは",)))

    def jobs(self) -> list[tuple[JobKind, str, JobStatus]]:
        return [(s.job.kind, s.job.target_id, s.job.status) for s in self.queue.list_all()]

    def titles(self) -> dict[str, tuple[str, ...]]:
        return {lecture.title: lecture.recording_ids for lecture in self.lectures.list_all()}


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    """録画ファイル r1〜r3 が、1 本ずつのレクチャー l1〜l3 になっている（取り込んだ直後）。"""
    conn = open_database(tmp_path / "db.sqlite3")
    recordings = SqliteRecordingRepository(conn)
    lectures = SqliteLectureRepository(conn)
    for n in (1, 2, 3):
        recordings.add(make_recording(tmp_path / f"S05-1{n}.mov", f"r{n}"))
        lectures.save(Lecture(id=f"l{n}", title=f"S05-1{n}", recording_ids=(f"r{n}",)))
    yield Env(
        conn=conn,
        store=DirectoryStore(tmp_path / "ws"),
        lectures=lectures,
        edit_states=SqliteEditStateRepository(conn),
        judgements=SqliteJudgementRepository(conn),
        queue=SqliteJobQueue(conn),
    )
    conn.close()


def cut(cut_id: str, recording_id: str) -> ManualCut:
    return ManualCut(id=cut_id, recording_id=recording_id, span=Interval(100, 200))


def retake(recording_id: str) -> CutSuggestion:
    return CutSuggestion(
        id=f"{recording_id}-c0000-judged",
        recording_id=recording_id,
        span=Interval(0, 1_000),
        kind=CutKind.RETAKE,
        reason="言い直し",
    )


class TestMerge:
    def test_joins_lectures_into_one_in_the_given_order(self, env: Env) -> None:
        merged = env.service().merge(["l2", "l1"])
        assert merged.recording_ids == ("r2", "r1")
        assert env.lectures.list_all() == (
            Lecture(id="l3", title="S05-13", recording_ids=("r3",)),
            merged,
        )

    def test_title_defaults_to_the_first_lecture(self, env: Env) -> None:
        assert env.service().merge(["l2", "l1"]).title == "S05-12"

    def test_given_title_is_normalized(self, env: Env) -> None:
        merged = env.service().merge(["l1", "l2"], title=" ガイド‮ ")
        assert merged.title == "ガイド"

    def test_long_title_is_shortened(self, env: Env) -> None:
        merged = env.service().merge(["l1", "l2"], title="あ" * (MAX_TITLE_CHARS + 1))
        assert merged.title == "あ" * MAX_TITLE_CHARS
        assert env.lectures.get(merged.id) == merged

    def test_title_with_nothing_visible_is_rejected(self, env: Env) -> None:
        with pytest.raises(InvalidInputError, match="レクチャー名"):
            env.service().merge(["l1", "l2"], title="​ ")
        assert len(env.lectures.list_all()) == 3

    @pytest.mark.parametrize("ids", [[], ["l1"], ["l1", "l1"], ["l1", "l2", "l1"]])
    def test_needs_two_or_more_different_lectures(self, env: Env, ids: list[str]) -> None:
        with pytest.raises(InvalidInputError):
            env.service().merge(ids)

    def test_unknown_lecture_changes_nothing(self, env: Env) -> None:
        with pytest.raises(NotFoundError):
            env.service().merge(["l1", "missing"])
        assert len(env.lectures.list_all()) == 3

    def test_edits_of_the_merged_lectures_are_carried_over(self, env: Env) -> None:
        first = EditState(lecture_id="l1", version=0).restore("r1-silence-0000")
        env.edit_states.save(first.add_manual_cut(cut("m1", "r1")))
        env.edit_states.save(EditState(lecture_id="l2", version=0).add_manual_cut(cut("m2", "r2")))
        merged = env.service().merge(["l1", "l2"])
        state = env.edit_states.get(merged.id)
        assert state.restored_suggestion_ids == {"r1-silence-0000"}
        assert state.manual_cuts == (cut("m1", "r1"), cut("m2", "r2"))

    def test_lectures_without_edits_start_with_an_empty_edit_state(self, env: Env) -> None:
        merged = env.service().merge(["l1", "l2"])
        assert env.edit_states.get(merged.id) == EditState(lecture_id=merged.id, version=0)

    def test_manual_cuts_with_the_same_id_are_kept_once(self, env: Env) -> None:
        env.edit_states.save(EditState(lecture_id="l1", version=0).add_manual_cut(cut("m", "r1")))
        env.edit_states.save(EditState(lecture_id="l2", version=0).add_manual_cut(cut("m", "r2")))
        merged = env.service().merge(["l1", "l2"])
        assert env.edit_states.get(merged.id).manual_cuts == (cut("m", "r1"),)

    def test_enqueues_a_judgement_of_the_whole_lecture(self, env: Env) -> None:
        env.analyzed("r1", "r2")
        merged = env.service().merge(["l1", "l2"])
        assert env.jobs() == [(JobKind.JUDGE_LECTURE, merged.id, JobStatus.QUEUED)]

    def test_judgement_waits_for_recordings_still_being_analyzed(self, env: Env) -> None:
        env.analyzed("r1")
        env.service().merge(["l1", "l2"])
        assert env.jobs() == []  # r2 の解析が終わったときに積まれる

    def test_waiting_jobs_of_the_merged_lectures_are_discarded(self, env: Env) -> None:
        env.queue.enqueue(Job(id="running", kind=JobKind.JUDGE_LECTURE, target_id="l1"))
        env.queue.claim_next()
        env.queue.enqueue(Job(id="judge", kind=JobKind.JUDGE_LECTURE, target_id="l1"))
        env.queue.enqueue(Job(id="export", kind=JobKind.EXPORT_MP4, target_id="l2"))
        env.queue.enqueue(Job(id="other", kind=JobKind.EXPORT_MP4, target_id="l3"))
        env.queue.enqueue(Job(id="analyze", kind=JobKind.ANALYZE_RECORDING, target_id="r1"))
        env.service().merge(["l1", "l2"])
        assert [s.job.id for s in env.queue.list_all()] == ["running", "other", "analyze"]

    def test_nothing_changes_when_the_edits_cannot_be_saved(self, env: Env) -> None:
        env.edit_states.save(EditState(lecture_id="l1", version=0).add_manual_cut(cut("m1", "r1")))
        env.queue.enqueue(Job(id="judge", kind=JobKind.JUDGE_LECTURE, target_id="l1"))
        with pytest.raises(sqlite3.OperationalError):
            env.service(_UnwritableEditStates(env.edit_states)).merge(["l1", "l2"])
        assert [lecture.id for lecture in env.lectures.list_all()] == ["l1", "l2", "l3"]
        assert env.edit_states.get("l1").manual_cuts == (cut("m1", "r1"),)
        assert [s.job.id for s in env.queue.list_all()] == ["judge"]


class _UnwritableEditStates:
    def __init__(self, inner: SqliteEditStateRepository) -> None:
        self._inner = inner

    def get(self, lecture_id: str) -> EditState:
        return self._inner.get(lecture_id)

    def save(self, state: EditState) -> EditState:
        raise sqlite3.OperationalError("database or disk is full")


class TestReorder:
    @pytest.fixture
    def merged(self, env: Env) -> Lecture:
        env.analyzed("r1", "r2")
        lecture = Lecture(id="l12", title="まとめ", recording_ids=("r1", "r2"))
        env.lectures.replace(remove=("l1", "l2"), save=(lecture,))
        return lecture

    def test_changes_the_order_and_enqueues_a_judgement(self, env: Env, merged: Lecture) -> None:
        reordered = env.service().reorder("l12", ["r2", "r1"])
        assert reordered == Lecture(id="l12", title="まとめ", recording_ids=("r2", "r1"))
        assert env.lectures.get("l12") == reordered
        assert env.jobs() == [(JobKind.JUDGE_LECTURE, "l12", JobStatus.QUEUED)]

    def test_same_order_does_nothing(self, env: Env, merged: Lecture) -> None:
        assert env.service().reorder("l12", ["r1", "r2"]) == merged
        assert env.jobs() == []

    def test_edits_and_judgement_stay_with_the_lecture(self, env: Env, merged: Lecture) -> None:
        env.edit_states.save(EditState(lecture_id="l12", version=0).add_manual_cut(cut("m", "r1")))
        env.judgements.save(Judgement("l12", "key", (retake("r1"),)))
        env.service().reorder("l12", ["r2", "r1"])
        assert env.edit_states.get("l12").manual_cuts == (cut("m", "r1"),)
        assert env.judgements.get("l12") is not None

    @pytest.mark.parametrize("ids", [["r1"], ["r1", "r3"], ["r1", "r2", "r3"], ["r1", "r1"]])
    def test_recordings_must_stay_the_same(self, env: Env, merged: Lecture, ids: list[str]) -> None:
        with pytest.raises(InvalidInputError, match="構成"):
            env.service().reorder("l12", ids)
        assert env.lectures.get("l12") == merged

    def test_unknown_lecture(self, env: Env) -> None:
        with pytest.raises(NotFoundError):
            env.service().reorder("missing", ["r1"])


class TestSplit:
    @pytest.fixture
    def merged(self, env: Env) -> Lecture:
        env.analyzed("r1", "r2")
        lecture = Lecture(id="l12", title="まとめ", recording_ids=("r2", "r1"))
        env.lectures.replace(remove=("l1", "l2"), save=(lecture,))
        return lecture

    def test_makes_one_lecture_per_recording_named_after_its_file(
        self, env: Env, merged: Lecture
    ) -> None:
        parts = env.service().split("l12")
        assert [(p.title, p.recording_ids) for p in parts] == [
            ("S05-12", ("r2",)),
            ("S05-11", ("r1",)),
        ]
        assert env.titles() == {"S05-13": ("r3",), "S05-12": ("r2",), "S05-11": ("r1",)}

    def test_file_name_with_nothing_visible_gets_the_fallback_title(
        self, env: Env, tmp_path: Path
    ) -> None:
        SqliteRecordingRepository(env.conn).add(make_recording(tmp_path / "\u200b.mov", "r4"))
        lecture = Lecture(id="l34", title="まとめ", recording_ids=("r3", "r4"))
        env.lectures.replace(remove=("l3",), save=(lecture,))
        assert [part.title for part in env.service().split("l34")] == ["S05-13", FALLBACK_TITLE]

    def test_manual_cuts_go_to_the_lecture_of_their_recording(
        self, env: Env, merged: Lecture
    ) -> None:
        state = EditState(lecture_id="l12", version=0)
        env.edit_states.save(state.add_manual_cut(cut("m1", "r1")).add_manual_cut(cut("m2", "r2")))
        first, second = env.service().split("l12")
        assert env.edit_states.get(first.id).manual_cuts == (cut("m2", "r2"),)
        assert env.edit_states.get(second.id).manual_cuts == (cut("m1", "r1"),)

    def test_restorations_follow_the_recording_of_their_suggestion(
        self, env: Env, merged: Lecture
    ) -> None:
        env.judgements.save(Judgement("l12", "key", (retake("r2"),)))
        state = EditState(lecture_id="l12", version=0)
        for suggestion_id in ("r1-silence-0000", "r2-c0000-judged", "gone"):
            state = state.restore(suggestion_id)
        env.edit_states.save(state)
        first, second = env.service().split("l12")
        # 無音の候補は解析結果から、言い直しの候補は判定結果から、どの録画ファイルのものかが分かる
        assert env.edit_states.get(first.id).restored_suggestion_ids == {"r2-c0000-judged"}
        assert env.edit_states.get(second.id).restored_suggestion_ids == {"r1-silence-0000"}

    def test_recording_without_edits_gets_an_empty_edit_state(
        self, env: Env, merged: Lecture
    ) -> None:
        env.edit_states.save(EditState(lecture_id="l12", version=0).add_manual_cut(cut("m", "r1")))
        first, _ = env.service().split("l12")
        assert env.edit_states.get(first.id) == EditState(lecture_id=first.id, version=0)

    def test_restorations_of_an_unreadable_analysis_are_dropped(
        self, env: Env, merged: Lecture, caplog: pytest.LogCaptureFixture
    ) -> None:
        env.edit_states.save(EditState(lecture_id="l12", version=0).restore("r1-silence-0000"))
        env.store.path("r1", "analysis.json").write_text("{broken")
        _, second = env.service().split("l12")
        assert env.edit_states.get(second.id).restored_suggestion_ids == frozenset()
        assert "r1" in caplog.text

    def test_restorations_of_a_recording_not_analyzed_yet_are_dropped(self, env: Env) -> None:
        env.analyzed("r1")
        lecture = Lecture(id="l13", title="まとめ", recording_ids=("r1", "r3"))
        env.lectures.replace(remove=("l1", "l3"), save=(lecture,))
        state = EditState(lecture_id="l13", version=0)
        env.edit_states.save(state.restore("r1-silence-0000").restore("r3-silence-0000"))
        first, second = env.service().split("l13")
        assert env.edit_states.get(first.id).restored_suggestion_ids == {"r1-silence-0000"}
        assert env.edit_states.get(second.id).restored_suggestion_ids == frozenset()

    def test_recording_that_is_no_longer_registered(self, env: Env, merged: Lecture) -> None:
        with pytest.raises(NotFoundError, match="録画ファイル"):
            env.service(recordings=NoRecordings()).split("l12")
        assert env.lectures.get("l12") == merged

    def test_each_part_is_judged_again(self, env: Env, merged: Lecture) -> None:
        first, second = env.service().split("l12")
        assert env.jobs() == [
            (JobKind.JUDGE_LECTURE, first.id, JobStatus.QUEUED),
            (JobKind.JUDGE_LECTURE, second.id, JobStatus.QUEUED),
        ]

    def test_waiting_jobs_of_the_split_lecture_are_discarded(
        self, env: Env, merged: Lecture
    ) -> None:
        env.queue.enqueue(Job(id="export", kind=JobKind.EXPORT_PREMIERE, target_id="l12"))
        env.service().split("l12")
        assert "export" not in [s.job.id for s in env.queue.list_all()]

    def test_lecture_with_one_recording_cannot_be_split(self, env: Env) -> None:
        with pytest.raises(InvalidInputError, match="まとめた"):
            env.service().split("l3")

    def test_unknown_lecture(self, env: Env) -> None:
        with pytest.raises(NotFoundError):
            env.service().split("missing")

    def test_nothing_changes_when_the_edits_cannot_be_saved(
        self, env: Env, merged: Lecture
    ) -> None:
        env.edit_states.save(EditState(lecture_id="l12", version=0).add_manual_cut(cut("m", "r1")))
        with pytest.raises(sqlite3.OperationalError):
            env.service(_UnwritableEditStates(env.edit_states)).split("l12")
        assert env.lectures.get("l12") == merged
        assert env.edit_states.get("l12").manual_cuts == (cut("m", "r1"),)


class TestReanalyze:
    def test_enqueues_an_analysis_of_every_recording(self, env: Env) -> None:
        env.lectures.replace(
            remove=("l1", "l2"), save=(Lecture(id="l12", title="t", recording_ids=("r2", "r1")),)
        )
        jobs = env.service().reanalyze("l12")
        assert [(j.kind, j.target_id) for j in jobs] == [
            (JobKind.ANALYZE_RECORDING, "r2"),
            (JobKind.ANALYZE_RECORDING, "r1"),
        ]
        assert env.jobs() == [
            (JobKind.ANALYZE_RECORDING, "r2", JobStatus.QUEUED),
            (JobKind.ANALYZE_RECORDING, "r1", JobStatus.QUEUED),
        ]

    def test_analysis_already_waiting_is_not_enqueued_twice(self, env: Env) -> None:
        service = env.service()
        first = service.reanalyze("l1")
        again = service.reanalyze("l1")
        assert again == first
        assert len(env.queue.list_all()) == 1

    def test_only_recordings_without_a_waiting_analysis_get_a_new_job(self, env: Env) -> None:
        env.lectures.replace(
            remove=("l1", "l2"), save=(Lecture(id="l12", title="t", recording_ids=("r1", "r2")),)
        )
        env.queue.enqueue(Job(id="waiting", kind=JobKind.ANALYZE_RECORDING, target_id="r1"))
        jobs = env.service().reanalyze("l12")
        assert [(j.id, j.target_id) for j in jobs] == [("waiting", "r1"), ("new0", "r2")]
        assert len(env.queue.list_all()) == 2

    def test_can_be_requested_again_after_the_analysis_started(self, env: Env) -> None:
        service = env.service()
        (first,) = service.reanalyze("l1")
        env.queue.claim_next()
        (again,) = service.reanalyze("l1")
        assert again.id != first.id

    def test_unknown_lecture(self, env: Env) -> None:
        with pytest.raises(NotFoundError):
            env.service().reanalyze("missing")

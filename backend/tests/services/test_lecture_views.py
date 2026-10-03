import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.pipeline.fakes import DirectoryStore, NoRecordings, make_recording
from tests.pipeline.judge_fakes import make_analysis
from vidcut.adapters.sqlite.database import open_database
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
    ErrorCode,
    Job,
    JobKind,
    JobStatus,
    Lecture,
)
from vidcut.pipeline.analysis_result import save_analysis
from vidcut.pipeline.ports import Judgement, NotFoundError, RecordingRepository
from vidcut.services.lecture_views import JobView, LectureQuery, LectureStatus, lecture_status

ANALYZE = JobKind.ANALYZE_RECORDING
JUDGE = JobKind.JUDGE_LECTURE
QUEUED, RUNNING, SUCCEEDED, FAILED = (
    JobStatus.QUEUED,
    JobStatus.RUNNING,
    JobStatus.SUCCEEDED,
    JobStatus.FAILED,
)


def job(kind: JobKind, status: JobStatus, target: str = "t") -> Job:
    return Job(id=f"{kind}-{target}-{status}", kind=kind, target_id=target, status=status)


class TestLectureStatus:
    @pytest.mark.parametrize(
        ("jobs", "status"),
        [
            ([], LectureStatus.READY),
            ([(ANALYZE, QUEUED)], LectureStatus.QUEUED),
            ([(ANALYZE, RUNNING)], LectureStatus.ANALYZING),
            ([(ANALYZE, SUCCEEDED), (JUDGE, QUEUED)], LectureStatus.QUEUED),
            ([(ANALYZE, SUCCEEDED), (JUDGE, RUNNING)], LectureStatus.JUDGING),
            ([(ANALYZE, SUCCEEDED), (JUDGE, SUCCEEDED)], LectureStatus.READY),
            ([(ANALYZE, FAILED)], LectureStatus.FAILED),
            ([(ANALYZE, SUCCEEDED), (JUDGE, FAILED)], LectureStatus.FAILED),
            # 動いているものがあるうちは、その状態を出す（失敗は終わってから出る）
            ([(ANALYZE, FAILED), (ANALYZE, RUNNING)], LectureStatus.ANALYZING),
            ([(ANALYZE, FAILED), (ANALYZE, QUEUED)], LectureStatus.QUEUED),
            ([(ANALYZE, RUNNING), (ANALYZE, QUEUED)], LectureStatus.ANALYZING),
            ([(ANALYZE, QUEUED), (JUDGE, RUNNING)], LectureStatus.JUDGING),
        ],
    )
    def test_status_comes_from_the_latest_jobs(
        self, jobs: list[tuple[JobKind, JobStatus]], status: LectureStatus
    ) -> None:
        assert lecture_status([job(kind, s) for kind, s in jobs]) is status


@dataclass
class Env:
    conn: sqlite3.Connection
    store: DirectoryStore
    lectures: SqliteLectureRepository
    edit_states: SqliteEditStateRepository
    judgements: SqliteJudgementRepository
    queue: SqliteJobQueue

    def query(self, recordings: RecordingRepository | None = None) -> LectureQuery:
        return LectureQuery(
            lectures=self.lectures,
            recordings=recordings or SqliteRecordingRepository(self.conn),
            edit_states=self.edit_states,
            judgements=self.judgements,
            store=self.store,
            queue=self.queue,
        )

    def finished(self, jid: str, kind: JobKind, target: str, *, failed: bool = False) -> None:
        """ジョブを積み、実行して終わらせる（ほかに待機中のジョブがないときに使う）。"""
        self.queue.enqueue(Job(id=jid, kind=kind, target_id=target))
        claimed = self.queue.claim_next()
        assert claimed is not None and claimed.id == jid
        if failed:
            self.queue.mark_failed(jid, "/Users/me/a.mov: boom", ErrorCode.TOOL_FAILED)
        else:
            self.queue.mark_succeeded(jid)


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    """レクチャー l1 は録画ファイル r2・r1（この順）、l2 は r3。"""
    conn = open_database(tmp_path / "db.sqlite3")
    recordings = SqliteRecordingRepository(conn)
    for rid in ("r1", "r2", "r3"):
        recordings.add(make_recording(tmp_path / f"{rid}.mov", rid))
    lectures = SqliteLectureRepository(conn)
    lectures.save(Lecture(id="l1", title="S05-12", recording_ids=("r2", "r1")))
    lectures.save(Lecture(id="l2", title="S05-13", recording_ids=("r3",)))
    yield Env(
        conn=conn,
        store=DirectoryStore(tmp_path / "ws"),
        lectures=lectures,
        edit_states=SqliteEditStateRepository(conn),
        judgements=SqliteJudgementRepository(conn),
        queue=SqliteJobQueue(conn),
    )
    conn.close()


class TestSummaries:
    def test_lists_lectures_with_their_recordings_in_order(self, env: Env) -> None:
        first, second = env.query().summaries()
        assert (first.lecture.id, [r.id for r in first.recordings]) == ("l1", ["r2", "r1"])
        assert (second.lecture.id, [r.id for r in second.recordings]) == ("l2", ["r3"])

    def test_status_uses_the_latest_job_of_each_recording_and_the_lecture(self, env: Env) -> None:
        env.finished("old", ANALYZE, "r1", failed=True)
        env.finished("a1", ANALYZE, "r1")  # 再実行して成功した
        env.finished("a2", ANALYZE, "r2")
        env.finished("j1", JUDGE, "l1", failed=True)
        env.queue.enqueue(Job(id="a3", kind=ANALYZE, target_id="r3"))
        first, second = env.query().summaries()
        assert first.status is LectureStatus.FAILED
        assert [j.id for j in first.jobs] == ["a2", "a1", "j1"]  # 録画ファイルの順、判定は最後
        assert first.jobs[-1].error_code is ErrorCode.TOOL_FAILED
        assert second.status is LectureStatus.QUEUED
        assert [j.id for j in second.jobs] == ["a3"]

    def test_jobs_carry_the_error_code_but_not_the_raw_error(self, env: Env) -> None:
        # 生のエラー文には絶対パスや外部ツールの出力が入る。API に渡す型には載せない
        env.finished("a3", ANALYZE, "r3", failed=True)
        _, second = env.query().summaries()
        (view,) = second.jobs
        assert view == JobView(
            id="a3",
            kind=ANALYZE,
            target_id="r3",
            status=FAILED,
            stage=None,
            progress=0.0,
            error_code=ErrorCode.TOOL_FAILED,
        )
        assert "/Users/me" not in repr(second)

    def test_mezzanine_and_export_jobs_do_not_change_the_status(self, env: Env) -> None:
        env.finished("a3", ANALYZE, "r3")
        env.finished("m3", JobKind.MAKE_MEZZANINE, "r3", failed=True)
        env.finished("e2", JobKind.EXPORT_MP4, "l2", failed=True)
        env.queue.enqueue(Job(id="x2", kind=JobKind.EXPORT_PREMIERE, target_id="l2"))
        _, second = env.query().summaries()
        assert second.status is LectureStatus.READY
        assert [j.id for j in second.jobs] == ["a3"]

    def test_lecture_whose_recording_is_no_longer_registered(self, env: Env) -> None:
        with pytest.raises(NotFoundError, match="録画ファイル"):
            env.query(NoRecordings()).summaries()


class TestDetail:
    def test_gathers_everything_the_editor_needs(self, env: Env) -> None:
        for rid in ("r1", "r2"):
            save_analysis(env.store, make_analysis(rid, ("こんにちは", "えーと")))
        retake = CutSuggestion(
            id="r2-c0000-judged",
            recording_id="r2",
            span=Interval(0, 1_000),
            kind=CutKind.RETAKE,
            reason="言い直し",
        )
        env.judgements.save(Judgement("l1", "key", (retake,), ("gone",)))
        saved = env.edit_states.save(EditState(lecture_id="l1", version=0).restore(retake.id))
        env.finished("a1", ANALYZE, "r1")
        detail = env.query().detail("l1")
        assert detail.summary.lecture.id == "l1"
        assert [r.id for r in detail.summary.recordings] == ["r2", "r1"]
        assert detail.summary.status is LectureStatus.READY
        assert list(detail.analyses) == ["r2", "r1"]
        assert [t.text for t in detail.analyses["r1"].tokens] == list("こんにちはえーと")
        assert detail.judgement == Judgement("l1", "key", (retake,), ("gone",))
        assert detail.edit_state == saved
        assert detail.unreadable_recording_ids == ()

    def test_recordings_not_analyzed_yet_have_no_analysis(self, env: Env) -> None:
        save_analysis(env.store, make_analysis("r1", ("a",)))
        detail = env.query().detail("l1")
        assert list(detail.analyses) == ["r1"]
        assert detail.judgement is None
        assert detail.edit_state == EditState(lecture_id="l1", version=0)

    def test_unreadable_analysis_is_reported_so_it_can_be_analyzed_again(
        self, env: Env, caplog: pytest.LogCaptureFixture
    ) -> None:
        save_analysis(env.store, make_analysis("r1", ("a",)))
        env.store.path("r2", "analysis.json").write_text('{"silences": []}')  # 古い形
        detail = env.query().detail("l1")
        assert list(detail.analyses) == ["r1"]
        assert detail.unreadable_recording_ids == ("r2",)
        assert "r2" in caplog.text

    def test_unknown_lecture(self, env: Env) -> None:
        with pytest.raises(NotFoundError):
            env.query().detail("missing")

import sqlite3
from pathlib import Path

import pytest

from vidcut.adapters.sqlite.database import open_database
from vidcut.adapters.sqlite.jobs import SqliteJobQueue
from vidcut.domain.models import ErrorCode, Job, JobKind, JobStatus
from vidcut.pipeline.ports import NotFoundError


@pytest.fixture
def queue(conn: sqlite3.Connection) -> SqliteJobQueue:
    return SqliteJobQueue(conn)


def job(jid: str, kind: JobKind = JobKind.ANALYZE_RECORDING) -> Job:
    return Job(id=jid, kind=kind, target_id=f"target-{jid}")


def status_of(queue: SqliteJobQueue, jid: str) -> JobStatus:
    stored = queue.get(jid)
    assert stored is not None
    return stored.job.status


class TestEnqueue:
    def test_stores_job_with_priority_of_its_kind(self, queue: SqliteJobQueue) -> None:
        queue.enqueue(job("j1", JobKind.MAKE_MEZZANINE))
        stored = queue.get("j1")
        assert stored is not None
        assert stored.job == job("j1", JobKind.MAKE_MEZZANINE)
        assert stored.priority == JobKind.MAKE_MEZZANINE.priority
        assert stored.created_at.tzinfo is not None

    def test_get_unknown_returns_none(self, queue: SqliteJobQueue) -> None:
        assert queue.get("nope") is None

    def test_rejects_duplicate_id(self, queue: SqliteJobQueue) -> None:
        queue.enqueue(job("j1"))
        with pytest.raises(ValueError):
            queue.enqueue(job("j1"))

    def test_lists_in_registration_order(self, queue: SqliteJobQueue) -> None:
        for jid in ["b", "a", "c"]:
            queue.enqueue(job(jid))
        assert [stored.job.id for stored in queue.list_all()] == ["b", "a", "c"]


class TestClaimNext:
    def test_returns_none_when_nothing_is_queued(self, queue: SqliteJobQueue) -> None:
        assert queue.claim_next() is None

    def test_marks_claimed_job_running(self, queue: SqliteJobQueue) -> None:
        queue.enqueue(job("j1"))
        claimed = queue.claim_next()
        assert claimed is not None
        assert claimed.status is JobStatus.RUNNING
        assert status_of(queue, "j1") is JobStatus.RUNNING
        assert queue.claim_next() is None

    def test_mezzanine_waits_for_other_jobs(self, queue: SqliteJobQueue) -> None:
        queue.enqueue(job("mezz", JobKind.MAKE_MEZZANINE))
        queue.enqueue(job("analyze"))
        queue.enqueue(job("judge", JobKind.JUDGE_LECTURE))
        order = [queue.claim_next() for _ in range(3)]
        assert [claimed.id for claimed in order if claimed] == ["analyze", "judge", "mezz"]

    def test_two_workers_never_claim_the_same_job(self, db_path: Path) -> None:
        first = SqliteJobQueue(open_database(db_path))
        second = SqliteJobQueue(open_database(db_path))
        first.enqueue(job("j1"))
        first.enqueue(job("j2"))
        claimed = [first.claim_next(), second.claim_next(), first.claim_next()]
        assert [c.id if c else None for c in claimed] == ["j1", "j2", None]


class TestProgressAndCompletion:
    def test_report_progress_records_stage(self, queue: SqliteJobQueue) -> None:
        queue.enqueue(job("j1"))
        queue.claim_next()
        queue.report_progress("j1", "transcribe", 0.4)
        stored = queue.get("j1")
        assert stored is not None
        assert (stored.job.stage, stored.job.progress) == ("transcribe", 0.4)
        assert stored.updated_at >= stored.created_at

    @pytest.mark.parametrize("progress", [-0.1, 1.1, float("nan")])
    def test_rejects_progress_outside_unit_range(
        self, queue: SqliteJobQueue, progress: float
    ) -> None:
        queue.enqueue(job("j1"))
        queue.claim_next()
        with pytest.raises(ValueError):
            queue.report_progress("j1", None, progress)

    def test_unknown_job_is_not_found(self, queue: SqliteJobQueue) -> None:
        with pytest.raises(NotFoundError):
            queue.report_progress("nope", None, 0.5)
        with pytest.raises(NotFoundError):
            queue.mark_succeeded("nope")

    def test_mark_succeeded_completes_progress(self, queue: SqliteJobQueue) -> None:
        queue.enqueue(job("j1"))
        queue.claim_next()
        queue.mark_succeeded("j1")
        stored = queue.get("j1")
        assert stored is not None
        assert (stored.job.status, stored.job.progress) == (JobStatus.SUCCEEDED, 1.0)

    def test_mark_failed_records_error(self, queue: SqliteJobQueue) -> None:
        queue.enqueue(job("j1"))
        queue.claim_next()
        queue.mark_failed("j1", "ffmpeg が失敗しました", ErrorCode.TOOL_FAILED)
        stored = queue.get("j1")
        assert stored is not None
        assert (stored.job.status, stored.job.error) == (JobStatus.FAILED, "ffmpeg が失敗しました")
        assert stored.job.error_code is ErrorCode.TOOL_FAILED

    def test_jobs_that_did_not_fail_have_no_error_code(self, queue: SqliteJobQueue) -> None:
        queue.enqueue(job("j1"))
        queue.claim_next()
        queue.mark_succeeded("j1")
        stored = queue.get("j1")
        assert stored is not None
        assert stored.job.error_code is None

    def test_only_running_jobs_can_finish(self, queue: SqliteJobQueue) -> None:
        queue.enqueue(job("j1"))
        with pytest.raises(ValueError, match="実行中"):
            queue.mark_succeeded("j1")
        with pytest.raises(ValueError, match="実行中"):
            queue.mark_failed("j1", "x", ErrorCode.INTERNAL)
        with pytest.raises(ValueError, match="実行中"):
            queue.report_progress("j1", None, 0.1)


class TestRecovery:
    def test_requeue_running_after_crash(self, queue: SqliteJobQueue) -> None:
        for jid in ["j1", "j2", "j3"]:
            queue.enqueue(job(jid))
        queue.claim_next()
        queue.claim_next()
        queue.mark_succeeded("j2")
        assert queue.requeue_running() == 1
        assert status_of(queue, "j1") is JobStatus.QUEUED
        assert status_of(queue, "j2") is JobStatus.SUCCEEDED
        claimed = queue.claim_next()
        assert claimed is not None
        assert claimed.id == "j1"  # 登録順を保つ

    def test_retry_resets_failed_job(self, queue: SqliteJobQueue) -> None:
        queue.enqueue(job("j1"))
        queue.claim_next()
        queue.report_progress("j1", "align", 0.7)
        queue.mark_failed("j1", "boom", ErrorCode.INTERNAL)
        queue.retry("j1")
        stored = queue.get("j1")
        assert stored is not None
        assert stored.job == job("j1")  # エラー文と種別も消える

    def test_retry_only_failed_jobs(self, queue: SqliteJobQueue) -> None:
        queue.enqueue(job("j1"))
        with pytest.raises(ValueError, match="失敗"):
            queue.retry("j1")
        with pytest.raises(NotFoundError):
            queue.retry("nope")

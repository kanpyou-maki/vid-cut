import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from vidcut.adapters.sqlite.database import open_database
from vidcut.adapters.sqlite.jobs import SqliteJobQueue
from vidcut.domain.models import ErrorCode, Job, JobKind, JobStatus
from vidcut.pipeline.ports import InvalidInputError, NotFoundError, StoredJob
from vidcut.services.job_control import JobControl


@pytest.fixture
def queue(tmp_path: Path) -> Iterator[SqliteJobQueue]:
    conn: sqlite3.Connection = open_database(tmp_path / "db.sqlite3")
    yield SqliteJobQueue(conn)
    conn.close()


def failed_job(queue: SqliteJobQueue, job_id: str = "j1") -> None:
    queue.enqueue(Job(id=job_id, kind=JobKind.ANALYZE_RECORDING, target_id="r1"))
    queue.claim_next()
    queue.mark_failed(job_id, "boom", ErrorCode.TOOL_FAILED)


class TestListAll:
    def test_lists_jobs_in_the_order_they_were_enqueued(self, queue: SqliteJobQueue) -> None:
        for job_id in ("j1", "j2"):
            queue.enqueue(Job(id=job_id, kind=JobKind.ANALYZE_RECORDING, target_id="r1"))
        assert [stored.job.id for stored in JobControl(queue).list_all()] == ["j1", "j2"]


class TestRetry:
    def test_puts_a_failed_job_back_in_the_queue(self, queue: SqliteJobQueue) -> None:
        failed_job(queue)
        stored = JobControl(queue).retry("j1")
        assert (stored.job.id, stored.job.status) == ("j1", JobStatus.QUEUED)
        assert (stored.job.error, stored.job.error_code) == (None, None)

    def test_only_failed_jobs_can_be_retried(self, queue: SqliteJobQueue) -> None:
        queue.enqueue(Job(id="j1", kind=JobKind.ANALYZE_RECORDING, target_id="r1"))
        with pytest.raises(InvalidInputError, match="失敗したジョブ"):
            JobControl(queue).retry("j1")

    def test_unknown_job(self, queue: SqliteJobQueue) -> None:
        with pytest.raises(NotFoundError):
            JobControl(queue).retry("nope")

    def test_job_that_disappears_during_the_retry(self, queue: SqliteJobQueue) -> None:
        class Vanishing(SqliteJobQueue):
            def get(self, job_id: str) -> StoredJob | None:
                return None

        failed_job(queue)
        with pytest.raises(NotFoundError):
            JobControl(Vanishing(queue._conn)).retry("j1")

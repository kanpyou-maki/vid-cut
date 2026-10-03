import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from vidcut.adapters.sqlite.database import open_database
from vidcut.adapters.sqlite.jobs import SqliteJobQueue
from vidcut.domain.models import ErrorCode, Job, JobKind
from vidcut.services.job_requests import find_queued


@pytest.fixture
def queue(tmp_path: Path) -> Iterator[SqliteJobQueue]:
    conn: sqlite3.Connection = open_database(tmp_path / "db.sqlite3")
    yield SqliteJobQueue(conn)
    conn.close()


class TestFindQueued:
    def test_finds_the_waiting_job_of_the_same_kind_and_target(self, queue: SqliteJobQueue) -> None:
        queue.enqueue(Job(id="other-kind", kind=JobKind.EXPORT_MP4, target_id="l1"))
        queue.enqueue(Job(id="other-target", kind=JobKind.JUDGE_LECTURE, target_id="l2"))
        queue.enqueue(Job(id="same", kind=JobKind.JUDGE_LECTURE, target_id="l1"))
        found = find_queued(queue, JobKind.JUDGE_LECTURE, "l1")
        assert found is not None
        assert found.id == "same"

    def test_running_and_finished_jobs_do_not_count(self, queue: SqliteJobQueue) -> None:
        for jid in ("running", "succeeded", "failed"):
            queue.enqueue(Job(id=jid, kind=JobKind.JUDGE_LECTURE, target_id="l1"))
            queue.claim_next()
        queue.mark_succeeded("succeeded")
        queue.mark_failed("failed", "boom", ErrorCode.INTERNAL)
        assert find_queued(queue, JobKind.JUDGE_LECTURE, "l1") is None

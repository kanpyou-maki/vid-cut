"""JobQueue の SQLite 実装。API サーバーと worker はこの表だけで連携する（ADR-004）。"""

import math
import sqlite3
from datetime import datetime

from vidcut.adapters.sqlite.database import NOW
from vidcut.domain.models import Job, JobKind, JobStatus
from vidcut.pipeline.ports import NotFoundError, StoredJob

_COLUMNS = "id, kind, target_id, status, priority, stage, progress, error, created_at, updated_at"


class SqliteJobQueue:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def enqueue(self, job: Job) -> None:
        try:
            self._conn.execute(
                "INSERT INTO jobs (id, kind, target_id, status, priority, stage, progress, error)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job.id,
                    job.kind.value,
                    job.target_id,
                    job.status.value,
                    job.kind.priority,
                    job.stage,
                    job.progress,
                    job.error,
                ),
            )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"同じ id のジョブが既にあります: {job.id}") from e

    def get(self, job_id: str) -> StoredJob | None:
        row = self._conn.execute(f"SELECT {_COLUMNS} FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _to_stored(row) if row else None

    def list_all(self) -> tuple[StoredJob, ...]:
        rows = self._conn.execute(f"SELECT {_COLUMNS} FROM jobs ORDER BY seq").fetchall()
        return tuple(_to_stored(row) for row in rows)

    def claim_next(self) -> Job | None:
        # 1 文で選んで更新するので、複数の worker が同じジョブを取ることはない
        row = self._conn.execute(
            f"UPDATE jobs SET status = 'running', updated_at = {NOW}"
            " WHERE seq = (SELECT seq FROM jobs WHERE status = 'queued'"
            "              ORDER BY priority DESC, seq LIMIT 1)"
            f" RETURNING {_COLUMNS}"
        ).fetchone()
        return _to_stored(row).job if row else None

    def report_progress(self, job_id: str, stage: str | None, progress: float) -> None:
        if not (math.isfinite(progress) and 0.0 <= progress <= 1.0):
            raise ValueError(f"progress は 0 以上 1 以下である必要があります: {progress}")
        self._update_running(job_id, "stage = ?, progress = ?", (stage, progress))

    def mark_succeeded(self, job_id: str) -> None:
        self._update_running(job_id, "status = 'succeeded', progress = 1", ())

    def mark_failed(self, job_id: str, error: str) -> None:
        self._update_running(job_id, "status = 'failed', error = ?", (error,))

    def requeue_running(self) -> int:
        cursor = self._conn.execute(
            f"UPDATE jobs SET status = 'queued', updated_at = {NOW} WHERE status = 'running'"
        )
        return cursor.rowcount

    def retry(self, job_id: str) -> None:
        cursor = self._conn.execute(
            "UPDATE jobs SET status = 'queued', stage = NULL, progress = 0, error = NULL,"
            f" updated_at = {NOW} WHERE id = ? AND status = 'failed'",
            (job_id,),
        )
        if cursor.rowcount == 0:
            self._require_exists(job_id)
            raise ValueError(f"再実行できるのは失敗したジョブだけです: {job_id}")

    def _update_running(
        self, job_id: str, assignments: str, params: tuple[str | float | None, ...]
    ) -> None:
        cursor = self._conn.execute(
            f"UPDATE jobs SET {assignments}, updated_at = {NOW}"
            " WHERE id = ? AND status = 'running'",
            (*params, job_id),
        )
        if cursor.rowcount == 0:
            self._require_exists(job_id)
            raise ValueError(f"ジョブが実行中ではありません: {job_id}")

    def _require_exists(self, job_id: str) -> None:
        if self.get(job_id) is None:
            raise NotFoundError(f"ジョブがありません: {job_id}")


def _to_stored(row: sqlite3.Row) -> StoredJob:
    return StoredJob(
        job=Job(
            id=row["id"],
            kind=JobKind(row["kind"]),
            target_id=row["target_id"],
            status=JobStatus(row["status"]),
            stage=row["stage"],
            progress=row["progress"],
            error=row["error"],
        ),
        priority=row["priority"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )

"""ジョブの一覧と、失敗したジョブの再実行（Design Doc 3-5 の /api/jobs）。"""

from vidcut.pipeline.ports import InvalidInputError, JobQueue, NotFoundError, StoredJob


class JobControl:
    def __init__(self, queue: JobQueue) -> None:
        self._queue = queue

    def list_all(self) -> tuple[StoredJob, ...]:
        """すべてのジョブ（登録順）。"""
        return self._queue.list_all()

    def retry(self, job_id: str) -> StoredJob:
        """失敗したジョブを待機中に戻して返す。失敗していないジョブは InvalidInputError。"""
        try:
            self._queue.retry(job_id)
        except ValueError as e:
            raise InvalidInputError("再実行できるのは失敗したジョブだけです") from e
        stored = self._queue.get(job_id)
        if stored is None:
            raise NotFoundError(f"ジョブがありません: {job_id}")
        return stored

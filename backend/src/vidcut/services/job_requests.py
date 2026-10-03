"""ジョブを積む前の確認。同じジョブが待機中なら、積み直さずにそれを使う。"""

from vidcut.domain.models import Job, JobKind, JobStatus
from vidcut.pipeline.ports import JobQueue


def find_queued(queue: JobQueue, kind: JobKind, target_id: str) -> Job | None:
    """同じ種類・同じ対象の待機中のジョブ。待機中のジョブは実行するときの状態を読むので、積み直す必要がない。

    確認と登録は 1 つの操作ではない。重なって二重に積まれても、2 本目は同じ結果を作り直すだけ。
    """
    for stored in queue.list_all():
        job = stored.job
        if (job.kind, job.target_id, job.status) == (kind, target_id, JobStatus.QUEUED):
            return job
    return None

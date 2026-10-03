"""/api/jobs: 進捗一覧と、失敗したジョブの再実行。"""

from fastapi import APIRouter

from vidcut.api.deps import PathId, Services
from vidcut.api.envelope import Envelope, ok
from vidcut.api.outputs import JobListItemOut
from vidcut.pipeline.ports import InvalidInputError, NotFoundError

router = APIRouter()


@router.get("/api/jobs")
def list_jobs(services: Services) -> Envelope[list[JobListItemOut]]:
    return ok([JobListItemOut.of_stored(stored) for stored in services.queue.list_all()])


@router.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: PathId, services: Services) -> Envelope[JobListItemOut]:
    try:
        services.queue.retry(job_id)
    except ValueError as e:
        raise InvalidInputError("再実行できるのは失敗したジョブだけです") from e
    stored = services.queue.get(job_id)
    if stored is None:
        raise NotFoundError(f"ジョブがありません: {job_id}")
    return ok(JobListItemOut.of_stored(stored))

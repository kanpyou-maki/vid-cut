"""/api/jobs: 進捗一覧と、失敗したジョブの再実行。"""

from fastapi import APIRouter

from vidcut.api.deps import PathId, Services
from vidcut.api.envelope import Envelope, ok
from vidcut.api.outputs import JobListItemOut
from vidcut.api.presenters import to_job_list_item

router = APIRouter()


@router.get("/api/jobs")
def list_jobs(services: Services) -> Envelope[list[JobListItemOut]]:
    return ok([to_job_list_item(stored) for stored in services.jobs.list_all()])


@router.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: PathId, services: Services) -> Envelope[JobListItemOut]:
    return ok(to_job_list_item(services.jobs.retry(job_id)))

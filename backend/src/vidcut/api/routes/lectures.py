"""/api/lectures: 一覧・詳細・まとめる・並べ替え・解除・再解析・編集の保存・書き出しの依頼。"""

from fastapi import APIRouter

from vidcut.api.deps import PathId, Services
from vidcut.api.envelope import Envelope, ok
from vidcut.api.schemas import (
    EditsIn,
    EditStateOut,
    ExportIn,
    JobOut,
    LectureDetailOut,
    LectureRefOut,
    LectureSummaryOut,
    MergeIn,
    OrderIn,
)

router = APIRouter()


@router.get("/api/lectures")
def list_lectures(services: Services) -> Envelope[list[LectureSummaryOut]]:
    summaries = services.lecture_views.summaries()
    return ok([LectureSummaryOut.of(summary) for summary in summaries])


@router.post("/api/lectures/merge")
def merge_lectures(body: MergeIn, services: Services) -> Envelope[LectureRefOut]:
    """渡した順に 1 つにまとめる（US-11）。判定ジョブを積む。"""
    return ok(LectureRefOut.of(services.lecture_service.merge(body.lecture_ids, body.title)))


@router.get("/api/lectures/{lecture_id}")
def get_lecture(lecture_id: PathId, services: Services) -> Envelope[LectureDetailOut]:
    return ok(LectureDetailOut.of(services.lecture_views.detail(lecture_id)))


@router.put("/api/lectures/{lecture_id}/order")
def reorder_lecture(
    lecture_id: PathId, body: OrderIn, services: Services
) -> Envelope[LectureRefOut]:
    lecture = services.lecture_service.reorder(lecture_id, body.recording_ids)
    return ok(LectureRefOut.of(lecture))


@router.post("/api/lectures/{lecture_id}/split")
def split_lecture(lecture_id: PathId, services: Services) -> Envelope[list[LectureRefOut]]:
    parts = services.lecture_service.split(lecture_id)
    return ok([LectureRefOut.of(part) for part in parts])


@router.post("/api/lectures/{lecture_id}/reanalyze")
def reanalyze_lecture(lecture_id: PathId, services: Services) -> Envelope[list[JobOut]]:
    """解析ロジックを更新したあとに、録画ファイルを解析し直す。終わると判定も積まれる。"""
    return ok([JobOut.of(job) for job in services.lecture_service.reanalyze(lecture_id)])


@router.put("/api/lectures/{lecture_id}/edits")
def save_edits(lecture_id: PathId, body: EditsIn, services: Services) -> Envelope[EditStateOut]:
    """version が保存済みの版と違えば 409（読み込み直してからやり直す）。"""
    return ok(EditStateOut.of(services.edits.save(body.to_domain(lecture_id))))


@router.post("/api/lectures/{lecture_id}/exports")
def request_export(lecture_id: PathId, body: ExportIn, services: Services) -> Envelope[JobOut]:
    """書き出しジョブを積む。同じ書き出しが待機中なら、そのジョブを返す。"""
    return ok(JobOut.of(services.exports.request(lecture_id, body.job_kind())))

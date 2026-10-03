"""/api/recordings: プレビュー用の動画（Range 対応）と波形のピーク値。"""

from fastapi import APIRouter
from fastapi.responses import FileResponse

from vidcut.api.deps import PathId, Services
from vidcut.api.envelope import Envelope, ok
from vidcut.api.outputs import PeaksOut
from vidcut.api.presenters import to_peaks

router = APIRouter()

PROXY_MEDIA_TYPE = "video/mp4"


@router.get(
    "/api/recordings/{recording_id}/proxy",
    response_class=FileResponse,
    responses={
        200: {"content": {PROXY_MEDIA_TYPE: {}}, "description": "動画の全体"},
        206: {"content": {PROXY_MEDIA_TYPE: {}}, "description": "Range で指定した部分"},
    },
)
def get_proxy(recording_id: PathId, services: Services) -> FileResponse:
    """<video> が読む。トークンは ?token= でも受け付ける（Design Doc 3-5-1）。"""
    return FileResponse(services.artifacts.proxy_path(recording_id), media_type=PROXY_MEDIA_TYPE)


@router.get("/api/recordings/{recording_id}/peaks")
def get_peaks(recording_id: PathId, services: Services) -> Envelope[PeaksOut]:
    return ok(to_peaks(services.artifacts.peaks(recording_id)))

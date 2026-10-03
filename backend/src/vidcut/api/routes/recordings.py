"""/api/recordings: プレビュー用の動画（Range 対応）と波形のピーク値。"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from vidcut.api.deps import PathId, Services
from vidcut.api.envelope import Envelope, ok
from vidcut.api.outputs import PeaksOut
from vidcut.bootstrap import ApiServices
from vidcut.pipeline.analysis import PEAKS_FILE, PROXY_FILE
from vidcut.pipeline.ports import NotFoundError

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
    proxy = _artifact(services, recording_id, PROXY_FILE)
    if not proxy.is_file():
        raise NotFoundError(f"プレビュー用の動画がまだありません: {recording_id}")
    return FileResponse(proxy, media_type=PROXY_MEDIA_TYPE)


@router.get("/api/recordings/{recording_id}/peaks")
def get_peaks(recording_id: PathId, services: Services) -> Envelope[PeaksOut]:
    _artifact(services, recording_id, PEAKS_FILE)
    data = services.store.read_json(recording_id, PEAKS_FILE)
    if data is None:
        raise NotFoundError(f"波形のピーク値がまだありません: {recording_id}")
    return ok(PeaksOut.model_validate(data))


def _artifact(services: ApiServices, recording_id: str, name: str) -> Path:
    """登録済みの録画ファイルの生成物の場所。未登録の id では、フォルダも作らない。"""
    if services.recordings.get(recording_id) is None:
        raise NotFoundError(f"録画ファイルが登録されていません: {recording_id}")
    return services.store.path(recording_id, name)

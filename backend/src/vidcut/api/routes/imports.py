"""POST /api/imports: 録画ファイルを登録し、解析ジョブを積む（US-10）。"""

from pathlib import Path

from fastapi import APIRouter

from vidcut.api.deps import Browser, Services
from vidcut.api.envelope import Envelope, ok
from vidcut.api.messages import ERROR_MESSAGES
from vidcut.api.schemas import ImportFailureOut, ImportIn, ImportResultOut
from vidcut.domain.models import ErrorCode
from vidcut.pipeline.ports import NotFoundError

router = APIRouter()


@router.post("/api/imports")
def import_paths(body: ImportIn, services: Services, browser: Browser) -> Envelope[ImportResultOut]:
    """ホームの外や隠しフォルダのパスが 1 つでもあれば、何も取り込まずに 422 を返す。

    見つからないパスは failed に入れ、ほかのパスの取り込みは続ける。
    フォルダは、その直下の動画ファイルに展開する。
    """
    targets: list[Path] = []
    missing: list[ImportFailureOut] = []
    for text in body.paths:
        try:
            targets.extend(browser.import_targets(Path(text)))
        except NotFoundError:
            code = ErrorCode.SOURCE_MISSING
            missing.append(ImportFailureOut(path=text, code=code, message=ERROR_MESSAGES[code]))
    result = services.imports.import_paths(targets)
    return ok(ImportResultOut.of(result, missing))

"""GET /api/fs: 投入するファイルとフォルダを選ぶための一覧（ホーム配下のみ）。"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Query

from vidcut.api.deps import Browser
from vidcut.api.envelope import Envelope, ok
from vidcut.api.inputs import MAX_PATH_CHARS
from vidcut.api.outputs import FsListingOut

router = APIRouter()


@router.get("/api/fs")
def list_directory(
    browser: Browser,
    path: Annotated[str | None, Query(min_length=1, max_length=MAX_PATH_CHARS)] = None,
) -> Envelope[FsListingOut]:
    listing = browser.list(None if path is None else Path(path))
    return ok(FsListingOut.of(listing))

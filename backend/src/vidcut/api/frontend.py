"""ビルド済み frontend の配信（Design Doc 2 章）。HTML には起動ごとのトークンを埋め込む（3-5-1）。

配信するのはビルドの出力（dist）の中のファイルだけ。ほかのパスには、画面の HTML を返す
（画面は 1 ページのアプリで、パスは画面の中で解釈する）。
"""

import html
import logging
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse, HTMLResponse, Response

TOKEN_META = "vidcut-token"
"""画面はこの名前の meta 要素からトークンを読み、X-VidCut-Token ヘッダーに付ける。"""

INDEX_FILE = "index.html"
_HEAD_END = "</head>"
_API_ROOT = "api"
# トークンは起動ごとに変わる。古いトークンの入ったページをブラウザに残さない
_NO_STORE = {"Cache-Control": "no-store"}
_NOT_BUILT = """<!doctype html>
<html lang="ja">
  <head><meta charset="UTF-8" /><title>vid-cut</title></head>
  <body>
    <p>画面（frontend）がビルドされていません。</p>
    <p>リポジトリのルートで <code>npm --prefix frontend run build</code> を実行してから、
       このページを読み込み直してください。API は利用できます。</p>
  </body>
</html>
"""

_logger = logging.getLogger(__name__)


def install_frontend(app: FastAPI, dist: Path | None, token: str) -> None:
    """API のルートを登録したあとに呼ぶ（/api 以外のすべての GET を受ける）。"""

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> Response:
        if path == _API_ROOT or path.startswith(_API_ROOT + "/"):
            # API の知らないパスに、画面の HTML を返さない
            raise HTTPException(status_code=404)
        asset = _asset(dist, path)
        if asset is not None:
            return FileResponse(asset)
        return _index(dist, token)


def _asset(dist: Path | None, path: str) -> Path | None:
    """dist の中の、隠しでないファイル。それ以外（外を指すパスやリンク、フォルダ）は None。"""
    if dist is None or not path or path == INDEX_FILE:
        return None
    root = dist.resolve()
    try:
        candidate = (root / path).resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    if any(part.startswith(".") for part in candidate.relative_to(root).parts):
        return None
    return candidate


def _index(dist: Path | None, token: str) -> HTMLResponse:
    """画面の HTML。読むたびにファイルを開く（ビルドし直したら、次の読み込みで反映される）。"""
    page = _read_index(dist)
    if page is None:
        return HTMLResponse(_NOT_BUILT, status_code=503, headers=_NO_STORE)
    tag = f'<meta name="{TOKEN_META}" content="{html.escape(token, quote=True)}" />'
    return HTMLResponse(page.replace(_HEAD_END, f"{tag}{_HEAD_END}", 1), headers=_NO_STORE)


def _read_index(dist: Path | None) -> str | None:
    """トークンを埋め込める画面の HTML。なければ None（ビルドの案内を返す）。"""
    if dist is None:
        return None
    try:
        page = (dist / INDEX_FILE).read_text(encoding="utf-8")
    except OSError:
        _logger.warning("画面の HTML を読めません: %s", dist / INDEX_FILE)
        return None
    if _HEAD_END not in page:
        _logger.warning("画面の HTML に </head> がなく、トークンを埋め込めません")
        return None
    return page

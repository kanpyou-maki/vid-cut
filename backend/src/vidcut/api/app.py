"""FastAPI のアプリの組み立て（Design Doc 3-5）。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from vidcut.api.envelope import ErrorOut
from vidcut.api.errors import install_error_handlers
from vidcut.api.frontend import frontend_fallback
from vidcut.api.headers import SecurityHeaders
from vidcut.api.routes import fs, imports, jobs, lectures, recordings, settings
from vidcut.api.security import ApiGuard, GuardSettings
from vidcut.bootstrap import Api
from vidcut.services.file_browser import FileBrowser

TITLE = "vid-cut API"

# どのエンドポイントも返しうる失敗。OpenAPI に実際の形（{success, data, error}）を載せる。
# 422 を自分で宣言すると、FastAPI 既定の HTTPValidationError は載らない
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorOut, "description": "トークンが正しくない"},
    403: {"model": ErrorOut, "description": "Host または Origin が受け付けられない"},
    404: {"model": ErrorOut, "description": "指定されたデータが見つからない"},
    422: {"model": ErrorOut, "description": "入力が正しくない"},
    500: {"model": ErrorOut, "description": "想定していない失敗（詳細はログ）"},
}


@dataclass(frozen=True)
class ApiSettings:
    guard: GuardSettings
    home: Path  # /api/fs と /api/imports が見せてよい範囲（利用者のホーム）
    frontend_dist: Path | None = None  # ビルド済み frontend の場所。None なら配信しない


def create_app(api: Api, settings: ApiSettings) -> FastAPI:
    """API と、ビルド済み frontend の配信。確認と制限は、すべての要求と応答にかける。"""
    app = _api_app()
    app.state.api = api
    app.state.browser = FileBrowser(settings.home)
    install_error_handlers(app, frontend_fallback(settings.frontend_dist, settings.guard.token))
    # 後に足したものが外側になる。断る応答にもヘッダーが付くよう、SecurityHeaders を外に置く
    app.add_middleware(ApiGuard, settings=settings.guard)
    app.add_middleware(SecurityHeaders)
    return app


def openapi_schema() -> dict[str, Any]:
    """API の OpenAPI スキーマ。frontend の型はここから作る（`vidcut openapi`）。"""
    return _api_app().openapi()


def _api_app() -> FastAPI:
    """API のルートだけを登録したアプリ。

    対話式のドキュメント（/docs）は出さない（画面の JS を外部の CDN から読むため）。
    """
    app = FastAPI(title=TITLE, docs_url=None, redoc_url=None, openapi_url=None)
    for module in (fs, imports, lectures, jobs, recordings, settings):
        app.include_router(module.router, responses=ERROR_RESPONSES)
    return app

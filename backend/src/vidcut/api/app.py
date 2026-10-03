"""FastAPI のアプリの組み立て（Design Doc 3-5）。"""

from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

from vidcut.api.errors import install_error_handlers
from vidcut.api.routes import fs, imports, jobs, lectures, recordings
from vidcut.api.security import ApiGuard, GuardSettings
from vidcut.bootstrap import Api
from vidcut.services.file_browser import FileBrowser

TITLE = "vid-cut API"


@dataclass(frozen=True)
class ApiSettings:
    guard: GuardSettings
    home: Path  # /api/fs と /api/imports が見せてよい範囲（利用者のホーム）


def create_app(api: Api, settings: ApiSettings) -> FastAPI:
    """対話式のドキュメント（/docs）は出さない（画面の JS を外部の CDN から読むため）。

    OpenAPI のスキーマは app.openapi() で取り出して、frontend の型の生成に使う。
    """
    app = FastAPI(title=TITLE, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.api = api
    app.state.browser = FileBrowser(settings.home)
    for module in (fs, imports, lectures, jobs, recordings):
        app.include_router(module.router)
    install_error_handlers(app)
    app.add_middleware(ApiGuard, settings=settings.guard)
    return app

"""ルートが受け取る依存。services はリクエストごとに自分の接続で組み立てる（Design Doc 3-5-2）。"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Path, Request

from vidcut.api.inputs import ID_PATTERN
from vidcut.bootstrap import ApiServices
from vidcut.services.file_browser import FileBrowser


def get_services(request: Request) -> Iterator[ApiServices]:
    with request.app.state.api.services() as services:
        yield services


def get_browser(request: Request) -> FileBrowser:
    browser: FileBrowser = request.app.state.browser
    return browser


Services = Annotated[ApiServices, Depends(get_services)]
Browser = Annotated[FileBrowser, Depends(get_browser)]
PathId = Annotated[str, Path(pattern=ID_PATTERN)]
"""URL に入る id（レクチャー・録画ファイル・ジョブ）。ファイル名にも使うので、文字を限る。"""

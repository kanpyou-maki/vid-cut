"""例外を `{success, data, error}` の応答に直す。応答には定型文だけを入れる（Design Doc 3-5-2）。

例外の文（str(e)）は絶対パスや外部ツールの出力を含みうるので、ログにだけ出す。
例外は InvalidInputError だけで、これは利用者の入力の誤りを説明するために書いた文を持つ。
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response

from vidcut.api import messages
from vidcut.api.envelope import failure
from vidcut.api.frontend import PageFallback
from vidcut.api.security import route_path
from vidcut.pipeline.ports import InvalidInputError, NotFoundError, VersionConflictError

_logger = logging.getLogger(__name__)


def install_error_handlers(app: FastAPI, page_fallback: PageFallback | None = None) -> None:
    """page_fallback は、どのルートにも当たらなかった GET に画面を返す（frontend.py）。"""

    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, error: NotFoundError) -> JSONResponse:
        _logger.info("%s %s: %s", request.method, request.url.path, error)
        return failure(404, messages.NOT_FOUND)

    @app.exception_handler(InvalidInputError)
    async def invalid_input(request: Request, error: InvalidInputError) -> JSONResponse:
        return failure(422, str(error))

    @app.exception_handler(VersionConflictError)
    async def conflict(request: Request, error: VersionConflictError) -> JSONResponse:
        return failure(409, messages.VERSION_CONFLICT)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        # どこが誤りかはログに出す（入力の値は出さない。応答にも入れない）
        places = [
            ".".join(str(part) for part in e["loc"]) + f"（{e['type']}）" for e in error.errors()
        ]
        _logger.info("%s %s: 入力が不正です: %s", request.method, request.url.path, places[:10])
        return failure(422, messages.INVALID_REQUEST)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> Response:
        if error.status_code == 404 and request.method == "GET" and page_fallback is not None:
            page = page_fallback(route_path(request.scope))
            if page is not None:
                return page
        message = messages.HTTP_ERRORS.get(error.status_code, messages.HTTP_ERROR_FALLBACK)
        return failure(error.status_code, message)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception) -> JSONResponse:
        _logger.error(
            "%s %s で想定していない例外が起きました",
            request.method,
            request.url.path,
            exc_info=error,
        )
        return failure(500, messages.SERVER_ERROR)

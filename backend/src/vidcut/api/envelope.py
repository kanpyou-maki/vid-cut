"""応答の形 `{success, data, error}`（.claude/rules/common/patterns.md、Design Doc 3-5）。"""

from typing import Literal

from pydantic import BaseModel
from starlette.responses import JSONResponse


class Envelope[T](BaseModel):
    """成功なら data、失敗なら error（利用者に見せてよい文）が入る。"""

    success: bool
    data: T | None = None
    error: str | None = None


class ErrorOut(BaseModel):
    """失敗の応答の形（OpenAPI に載せる。frontend の型はここから作る）。"""

    success: Literal[False]
    data: None
    error: str


def ok[T](data: T) -> Envelope[T]:
    return Envelope(success=True, data=data)


def failure(status: int, message: str) -> JSONResponse:
    """失敗の応答。message には定型文か、利用者の入力の誤りを説明する文だけを渡す。"""
    return JSONResponse({"success": False, "data": None, "error": message}, status_code=status)

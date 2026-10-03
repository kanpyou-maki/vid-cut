"""失敗を種別に分ける（Design Doc 3-5-2）。API は種別だけを返し、生のエラー文は返さない。"""

from vidcut.domain.models import ErrorCode
from vidcut.pipeline.judge import JudgeOutputError
from vidcut.pipeline.ports import (
    ExternalToolError,
    LoginRequiredError,
    NotFoundError,
    NothingToExportError,
    UnsupportedMediaError,
    VersionConflictError,
)

# 上から順に調べる。派生した型（LoginRequiredError など）を、元の型より先に置く
_CODES: tuple[tuple[type[BaseException], ErrorCode], ...] = (
    (LoginRequiredError, ErrorCode.LOGIN_REQUIRED),
    (ExternalToolError, ErrorCode.TOOL_FAILED),
    (UnsupportedMediaError, ErrorCode.UNSUPPORTED_MEDIA),
    (FileNotFoundError, ErrorCode.SOURCE_MISSING),
    (NotFoundError, ErrorCode.NOT_FOUND),
    (VersionConflictError, ErrorCode.CONFLICT),
    (JudgeOutputError, ErrorCode.INVALID_OUTPUT),
    (NothingToExportError, ErrorCode.NOTHING_TO_EXPORT),
)


def classify_error(error: BaseException) -> ErrorCode:
    """例外の型から種別を決める。どれにも当たらなければ internal（詳細はログで調べる）。"""
    for error_type, code in _CODES:
        if isinstance(error, error_type):
            return code
    return ErrorCode.INTERNAL

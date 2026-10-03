import pytest

from vidcut.domain.models import ErrorCode
from vidcut.pipeline.error_codes import classify_error
from vidcut.pipeline.judge import JudgeOutputError
from vidcut.pipeline.ports import (
    ExternalToolError,
    LoginRequiredError,
    NotFoundError,
    NothingToExportError,
    UnsupportedMediaError,
    VersionConflictError,
)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (LoginRequiredError("claude を起動して /login"), ErrorCode.LOGIN_REQUIRED),
        (ExternalToolError("ffmpeg が失敗しました: /Users/me/a.mov"), ErrorCode.TOOL_FAILED),
        (UnsupportedMediaError("音声のトラックがありません"), ErrorCode.UNSUPPORTED_MEDIA),
        (FileNotFoundError("元の録画ファイルが見つかりません"), ErrorCode.SOURCE_MISSING),
        (NotFoundError("レクチャーがありません"), ErrorCode.NOT_FOUND),
        (VersionConflictError("更新され続けています"), ErrorCode.CONFLICT),
        (JudgeOutputError("JSON として読めません"), ErrorCode.INVALID_OUTPUT),
        (NothingToExportError("残す区間がありません"), ErrorCode.NOTHING_TO_EXPORT),
        (ValueError("形が壊れています"), ErrorCode.INTERNAL),
        (RuntimeError("boom"), ErrorCode.INTERNAL),
        (PermissionError("読めません"), ErrorCode.INTERNAL),
    ],
)
def test_errors_are_sorted_into_codes_by_type(error: Exception, code: ErrorCode) -> None:
    assert classify_error(error) is code


def test_every_code_has_an_error_that_maps_to_it() -> None:
    # 種別を足したのに分類を足し忘れる、を防ぐ
    errors: list[Exception] = [
        LoginRequiredError(""),
        ExternalToolError(""),
        UnsupportedMediaError(""),
        FileNotFoundError(""),
        NotFoundError(""),
        VersionConflictError(""),
        JudgeOutputError(""),
        NothingToExportError(""),
        RuntimeError(""),
    ]
    assert {classify_error(e) for e in errors} == set(ErrorCode)

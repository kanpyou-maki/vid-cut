"""失敗の種別ごとの定型文（Design Doc 3-5-2）。画面には種別とこの文だけを出す。

生のエラー文（絶対パスや ffmpeg / claude の出力を含む）は、ここを通さずに返さないこと。
"""

from vidcut.domain.models import ErrorCode

LOG_HINT = "詳しくは vidcut serve を起動したターミナルのログを確認してください"

ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.LOGIN_REQUIRED: (
        "claude にログインしていません。"
        "ターミナルで claude を起動して /login を実行し、再実行してください"
    ),
    ErrorCode.TOOL_FAILED: f"外部ツール（ffmpeg または claude）の実行に失敗しました。{LOG_HINT}",
    ErrorCode.UNSUPPORTED_MEDIA: (
        "この形式の録画ファイルは処理できません（映像と音声の両方が必要です）"
    ),
    ErrorCode.SOURCE_MISSING: (
        "録画ファイルが見つかりません。移動や削除をしていないか確認してください"
    ),
    ErrorCode.NOT_FOUND: (
        "対象のレクチャーまたは録画ファイルがなくなったか、解析がまだ終わっていません"
    ),
    ErrorCode.CONFLICT: "編集状態が更新され続けたため、反映できませんでした。再実行してください",
    ErrorCode.INVALID_OUTPUT: "言い直しの判定の結果を読み取れませんでした。再実行してください",
    ErrorCode.NOTHING_TO_EXPORT: "残す区間がありません（すべて削除されています）",
    ErrorCode.INTERNAL: f"想定していない問題が起きました。{LOG_HINT}",
}

NOT_FOUND = "指定されたデータが見つかりません"
VERSION_CONFLICT = (
    "編集状態がほかの画面または判定のやり直しで更新されています。読み込み直してください"
)
INVALID_REQUEST = "入力の形式が正しくありません"
SERVER_ERROR = f"サーバーで問題が起きました。{LOG_HINT}"
REVEAL_FAILED = f"Finder で開けませんでした。{LOG_HINT}"
HTTP_ERRORS: dict[int, str] = {
    404: "この URL はありません",
    405: "この操作はできません",
}
HTTP_ERROR_FALLBACK = "要求を処理できません"

# ローカル API の防御（security.py）が要求を断るときの文
REFUSED_HOST = "この Host からは利用できません"
REFUSED_ORIGIN = "このページからは利用できません"
REFUSED_TOKEN = "トークンが正しくありません。ページを読み込み直してください"
REPEATED_HEADER = "同じヘッダーが重複しています"
BODY_LENGTH_REQUIRED = "本文の長さ（Content-Length）が必要です"
BODY_LENGTH_INVALID = "Content-Length が正しくありません"
BODY_TOO_LARGE = "本文が大きすぎます"
BODY_NOT_JSON = "本文は application/json で送ってください"


def error_message(code: ErrorCode | None, *, failed: bool) -> str | None:
    """失敗したジョブに出す文。種別が記録される前（古い版）の失敗は internal として扱う。"""
    if not failed:
        return None
    return ERROR_MESSAGES[code or ErrorCode.INTERNAL]

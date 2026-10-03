"""ローカル API の防御（Design Doc 3-5-1）。

127.0.0.1 で待ち受けるだけでは、ブラウザで開いた別のページからの要求（CSRF）や
DNS rebinding を防げない。すべての要求をここで確かめてから、アプリに渡す。
"""

import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import parse_qs

from starlette.types import ASGIApp, Receive, Scope, Send

from vidcut.api.envelope import failure

TOKEN_HEADER = "X-VidCut-Token"
TOKEN_QUERY = "token"
API_PREFIX = "/api/"
DEFAULT_MAX_BODY_BYTES = 1_000_000
MIN_TOKEN_CHARS = 32
LOCAL_HOSTS = ("127.0.0.1", "localhost")

# <video> はヘッダーを付けられないので、この経路だけはトークンをクエリでも受け取る
_QUERY_TOKEN_PATH = re.compile(r"/api/recordings/[^/]+/proxy")
_WRITING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_JSON = "application/json"


@dataclass(frozen=True)
class GuardSettings:
    token: str
    hosts: frozenset[str]  # 受け付ける Host ヘッダー
    origins: frozenset[str]  # 受け付ける Origin ヘッダー（ないときは同一オリジンの要求）
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES


def local_guard(
    token: str,
    *,
    port: int,
    dev_origins: tuple[str, ...] = (),
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
) -> GuardSettings:
    """127.0.0.1 と localhost の port だけを受け付ける設定。dev_origins は開発中の Vite 用。"""
    if len(token) < MIN_TOKEN_CHARS:
        raise ValueError(f"トークンが短すぎます（{MIN_TOKEN_CHARS} 文字以上にしてください）")
    hosts = frozenset(f"{host}:{port}" for host in LOCAL_HOSTS)
    return GuardSettings(
        token=token,
        hosts=hosts,
        origins=frozenset(f"http://{host}" for host in hosts) | frozenset(dev_origins),
        max_body_bytes=max_body_bytes,
    )


def new_token() -> str:
    """起動ごとに作るトークン（推測できない 256 ビット）。"""
    return secrets.token_urlsafe(32)


class ApiGuard:
    """すべての HTTP の要求を確かめる ASGI ミドルウェア。通らなければ、アプリには渡さない。"""

    def __init__(self, app: ASGIApp, settings: GuardSettings) -> None:
        self._app = app
        self._settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        refusal = self._check(scope)
        if refusal is None:
            await self._app(scope, receive, send)
            return
        status, message = refusal
        await failure(status, message)(scope, receive, send)

    def _check(self, scope: Scope) -> tuple[int, str] | None:
        headers = {name.decode("latin-1"): value for name, value in scope["headers"]}
        # DNS rebinding: 攻撃者の名前が 127.0.0.1 を指しても、Host は攻撃者の名前のまま届く
        if _text(headers, "host") not in self._settings.hosts:
            return 403, "この Host からは利用できません"
        # Origin が付くのは別のページからの要求か、書き込みの要求。CORS は許可しない
        if "origin" in headers and _text(headers, "origin") not in self._settings.origins:
            return 403, "このページからは利用できません"
        path: str = scope["path"]
        if not path.startswith(API_PREFIX):
            return None
        if not self._has_token(path, headers, scope["query_string"]):
            return 401, "トークンが正しくありません。ページを読み込み直してください"
        if scope["method"] in _WRITING_METHODS:
            return self._check_body(headers)
        return None

    def _has_token(self, path: str, headers: Mapping[str, bytes], query: bytes) -> bool:
        candidates = [headers.get(TOKEN_HEADER.lower(), b"")]
        if _QUERY_TOKEN_PATH.fullmatch(path):
            values = parse_qs(query.decode("latin-1")).get(TOKEN_QUERY, [])
            candidates.extend(value.encode("latin-1") for value in values)
        expected = self._settings.token.encode()
        # 一致の判定にかかる時間から、トークンを 1 文字ずつ探られないようにする
        return any(secrets.compare_digest(candidate, expected) for candidate in candidates)

    def _check_body(self, headers: Mapping[str, bytes]) -> tuple[int, str] | None:
        """本文は JSON だけ、長さが分かるものだけ、上限までを受け付ける。"""
        if "transfer-encoding" in headers:
            return 411, "本文の長さ（Content-Length）が必要です"
        try:
            length = int(_text(headers, "content-length") or "0")
        except ValueError:
            return 400, "Content-Length が正しくありません"
        if length < 0:
            return 400, "Content-Length が正しくありません"
        if length > self._settings.max_body_bytes:
            return 413, "本文が大きすぎます"
        # フォームから送れる形式（text/plain など）を受け付けない。JSON は別のページからは
        # 事前確認（preflight）なしに送れず、CORS を許可していないので届かない
        media_type = _text(headers, "content-type").split(";")[0].strip().lower()
        if length > 0 and media_type != _JSON:
            return 415, "本文は application/json で送ってください"
        return None


def _text(headers: Mapping[str, bytes], name: str) -> str:
    return headers.get(name, b"").decode("latin-1")

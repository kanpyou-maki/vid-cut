"""すべての応答に付ける、ブラウザの振る舞いを制限するヘッダー（Design Doc 3-5-1）。"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# 読み込めるのは自分自身（'self'）のものだけ。スクリプトのインライン実行は許可しない。
# スタイルのインラインは、波形の部品（wavesurfer.js）が style 要素を差し込むので許可する。
# 動画と画像は、画面が作る blob: と data: も使う。
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "media-src 'self' blob:",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
        "form-action 'none'",
    ]
)

SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    # 中身から種類を推測させない（JSON やテキストをスクリプトとして実行させない）
    "X-Content-Type-Options": "nosniff",
    # proxy 動画の URL には ?token= が付く。ほかのサイトへ Referer として送らない
    "Referrer-Policy": "no-referrer",
    # ほかのページの枠の中に表示させない（クリックジャッキング対策）
    "X-Frame-Options": "DENY",
}


class SecurityHeaders:
    """応答に SECURITY_HEADERS を足す ASGI ミドルウェア。

    要求を断る応答にも付くよう、いちばん外側に置く。
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers[name] = value
            await send(message)

        await self._app(scope, receive, send_with_headers)

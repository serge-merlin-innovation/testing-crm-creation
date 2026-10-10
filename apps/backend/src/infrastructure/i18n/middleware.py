import gzip
import json

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .localize import localize, resolve_language

LANGUAGE_COOKIE = "lang"


def request_language(request: Request) -> str:
    """The signed-in user's setting, else the UI's `lang` cookie, else Accept-Language."""
    chosen = getattr(request.state, "language", None)
    if chosen:
        return resolve_language(chosen).value
    cookie = request.cookies.get(LANGUAGE_COOKIE)
    if cookie:
        return resolve_language(cookie).value
    return resolve_language(request.headers.get("accept-language")).value


def _localized(payload: object, language: str) -> object:
    if not isinstance(payload, dict):
        return payload
    detail = payload.get("detail")
    if isinstance(detail, str):
        payload["detail"] = localize(detail, language)
    elif isinstance(detail, dict) and isinstance(detail.get("message"), str):
        detail["message"] = localize(detail["message"], language)
    for error in payload.get("errors") or []:
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            error["message"] = localize(error["message"], language)
    return payload


class LocalizeErrorsMiddleware:
    """Rewrites the English text of every 4xx/5xx JSON body into the caller's language (NFR-04 c1).

    Pure ASGI, so it sees the user language that the auth dependency stores on `request.state`.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        start: Message | None = None
        chunks: list[bytes] = []

        async def capture(message: Message) -> None:
            nonlocal start
            if message["type"] == "http.response.start":
                headers = MutableHeaders(raw=message["headers"])
                if message["status"] < 400 or "application/json" not in headers.get("content-type", ""):
                    await send(message)
                    start = None
                    chunks.append(b"\x00passthrough")
                    return
                start = message
                return
            if chunks[:1] == [b"\x00passthrough"]:
                await send(message)
                return
            chunks.append(message.get("body", b""))
            if message.get("more_body"):
                return
            body = b"".join(chunks)
            language = request_language(request)
            assert start is not None
            headers = MutableHeaders(raw=start["headers"])
            if headers.get("content-encoding") == "gzip":
                # GZip sits inside this middleware; error bodies are small, so send them plain.
                body = gzip.decompress(body)
                del headers["content-encoding"]
            if language != "en":
                try:
                    body = json.dumps(_localized(json.loads(body), language), ensure_ascii=False).encode()
                except ValueError:
                    pass
            headers["content-length"] = str(len(body))
            headers["content-language"] = language
            await send(start)
            await send({"type": "http.response.body", "body": body})

        await self.app(scope, receive, capture)

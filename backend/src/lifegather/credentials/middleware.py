import anyio
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class CredentialBodyLimit:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or not scope.get("path", "").startswith(
                (
                    "/api/credentials",
                    "/api/mailboxes",
                    "/api/scans",
                    "/api/appearance",
                    "/api/profiles",
                    "/api/documents/text",
                    "/api/documents/delete",
                    "/auth/email/",
                    "/auth/test-login",
                    "/api/chat",
                    "/api/memories",
                    "/api/assets",
                    "/api/photos/delete",
                    "/api/photos/detach",
                    "/api/photos/attach",
                    "/api/reviews",
                    "/api/receipts",
                )
            )
            or scope.get("method") not in {"POST", "PUT"}
        ):
            await self.app(scope, receive, send)
            return
        limit = 16384 if scope.get("path", "").startswith("/auth/email/") else 32768
        body = bytearray()
        try:
            with anyio.fail_after(10):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > limit:
                        await JSONResponse(
                            {"detail": "Request too large"},
                            status_code=413,
                            headers={"Cache-Control": "no-store"},
                        )(scope, receive, send)
                        return
                    body.extend(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await JSONResponse(
                {"detail": "Request timed out"},
                status_code=408,
                headers={"Cache-Control": "no-store"},
            )(scope, receive, send)
            return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

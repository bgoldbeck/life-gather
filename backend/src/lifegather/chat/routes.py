import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from lifegather.auth.routes import require_session, require_write_session
from lifegather.auth.store import CurrentSession
from lifegather.chat.runner import answer
from lifegather.chat.service import ChatService, TurnInput
from lifegather.memory.service import MemoryError

Authenticated = Annotated[CurrentSession, Depends(require_session)]
Mutation = Annotated[CurrentSession, Depends(require_write_session)]
Cursor = Annotated[str, Query(max_length=36)]


def service(request: Request) -> ChatService:
    return ChatService(request.app.state.auth_store.engine)


def chat_router() -> APIRouter:
    router = APIRouter(prefix="/api/chat")

    @router.get("/conversations")
    def conversations(
        request: Request, current: Authenticated, cursor: Cursor = ""
    ) -> dict[str, Any]:
        return service(request).conversations(current.user, cursor)

    @router.post("/conversations", status_code=201)
    def create(request: Request, current: Mutation) -> dict[str, Any]:
        return service(request).create(current.user)

    @router.get("/usage")
    def usage(request: Request, current: Authenticated) -> dict[str, Any]:
        return service(request).usage(current.user)

    @router.get("/sources/{source_id}")
    def source(
        request: Request,
        source_id: str,
        current: Authenticated,
        offset: Annotated[int, Query(ge=0, le=20000)] = 0,
    ) -> dict[str, Any]:
        original = service(request).memory.get_source(current.user, source_id)
        if offset > len(original.text):
            raise MemoryError("Invalid source offset")
        return {
            "id": original.id,
            "text": original.text[offset : offset + 4000],
            "next_offset": offset + 4000
            if offset + 4000 < len(original.text)
            else None,
            "recorded_at": original.recorded_at,
            "event_date": original.event_date,
            "source_type": original.source_type,
        }

    @router.get("/conversations/{conversation_id}/turns")
    def turns(
        request: Request,
        conversation_id: str,
        current: Authenticated,
        cursor: Cursor = "",
    ) -> dict[str, Any]:
        return service(request).turns(current.user, conversation_id, cursor)

    @router.post("/requests/{request_id}/cancel")
    def cancel(request: Request, request_id: str, current: Mutation) -> dict[str, Any]:
        return service(request).cancel(current.user, request_id)

    @router.post("/conversations/{conversation_id}/turns")
    async def send(
        request: Request, conversation_id: str, body: TurnInput, current: Mutation
    ) -> dict[str, Any]:
        chat = service(request)
        row, fresh = chat.begin(current.user, conversation_id, body)
        if not fresh:
            return row
        turn_id = row["id"]

        def active() -> None:
            refreshed = require_session(request)
            if refreshed.user.id != current.user.id:
                raise HTTPException(401, "Sign in required")
            # Reuse the pending row check without changing state.
            from sqlalchemy import select
            from sqlalchemy.orm import Session

            from lifegather.chat.models import Turn

            with Session(chat.engine) as db:
                state = db.scalar(
                    select(Turn.state).where(
                        Turn.user_id == current.user.id, Turn.id == turn_id
                    )
                )
            if state != "pending":
                raise asyncio.CancelledError

        async def guarded() -> dict[str, Any]:
            semaphore: asyncio.Semaphore = request.app.state.chat_slots
            if semaphore.locked():
                raise MemoryError("Chat is busy; try again shortly")
            async with semaphore, asyncio.timeout(65):
                return await answer(
                    chat,
                    current.user,
                    conversation_id,
                    body,
                    request.app.state.private_settings,
                    request.app.state.chat_provider,
                    active,
                )

        task = asyncio.create_task(guarded())
        try:
            while not task.done():
                await asyncio.wait({task}, timeout=0.25)
                active()
            result = task.result()
            active()
            return chat.finish(current.user, turn_id, result)
        except asyncio.CancelledError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            return chat.finish(
                current.user, turn_id, {"text": "Request stopped."}, "canceled"
            )
        except Exception:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            return chat.finish(
                current.user,
                turn_id,
                {
                    "text": "Unable to finish. Check Settings, model access, and "
                    "daily usage. Your message is preserved; "
                    "no automatic retry was made."
                },
                "failed",
            )

    return router

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import Path as PathParam
from fastapi.responses import StreamingResponse

from lifegather.assets.actions import ActionService
from lifegather.auth.routes import require_session, require_write_session
from lifegather.auth.store import CurrentSession
from lifegather.chat.context import ContextRead, WorkspaceContexts
from lifegather.chat.organizer import HELP
from lifegather.chat.preferences import ChatChoice, ChatPreferences
from lifegather.chat.privacy import (
    ConversationDelete,
    ConversationPreview,
    ConversationPrivacy,
    ConversationToken,
)
from lifegather.chat.runner import answer
from lifegather.chat.service import ChatService, SaveText, TurnInput
from lifegather.chat.streaming import DeltaSink
from lifegather.documents.service import DocumentService
from lifegather.memory.notes import CorrectionInput, NoteService
from lifegather.memory.service import MemoryError
from lifegather.photos.service import PhotoService
from lifegather.reconciliation.proposals import (
    ProposalPreview,
    ProposalReview,
    ProposalService,
)
from lifegather.reconciliation.receipts import ReceiptService

Authenticated = Annotated[CurrentSession, Depends(require_session)]
Mutation = Annotated[CurrentSession, Depends(require_write_session)]
Cursor = Annotated[str, Query(max_length=36)]


def service(request: Request) -> ChatService:
    return ChatService(request.app.state.auth_store.engine)


def chat_router() -> APIRouter:
    router = APIRouter(prefix="/api/chat")

    @router.post("/context")
    def workspace_context(
        request: Request, body: ContextRead, current: Authenticated
    ) -> dict[str, Any]:
        return WorkspaceContexts(service(request).engine).read(current.user, body)

    @router.get("/preferences")
    def preferences(request: Request, current: Authenticated) -> ChatChoice:
        return ChatPreferences(service(request).engine).get(current.user)

    @router.put("/preferences", status_code=204)
    def save_preferences(request: Request, current: Mutation, body: ChatChoice) -> None:
        ChatPreferences(service(request).engine).set(current.user, body)

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
            "photo": PhotoService(service(request).engine).source_photo(
                current.user, source_id
            ),
            "asset_context": ActionService(service(request).engine).source_context(
                current.user, source_id
            ),
            "asset_proposal_id": ProposalService(service(request).engine).for_source(
                current.user, source_id
            ),
            "document": DocumentService(service(request).engine).source_document(
                current.user, source_id
            ),
            "receipt_proposal_id": ReceiptService(service(request).engine).for_source(
                current.user, source_id
            ),
            "note": NoteService(service(request).engine).describe(
                current.user, source_id
            ),
        }

    @router.post("/sources/{source_id}/corrections")
    def correct_note(
        request: Request,
        source_id: Annotated[str, PathParam(min_length=1, max_length=36)],
        body: SaveText,
        current: Mutation,
    ) -> dict[str, Any]:
        return NoteService(service(request).engine).correct(
            current.user, CorrectionInput(source_id=source_id, **body.model_dump())
        )

    @router.get("/sources/{source_id}/history")
    def note_history(
        request: Request,
        source_id: Annotated[str, PathParam(min_length=1, max_length=36)],
        current: Authenticated,
        cursor: Cursor = "",
        limit: Annotated[int, Query(ge=1, le=25)] = 25,
    ) -> dict[str, Any]:
        return NoteService(service(request).engine).history(
            current.user, source_id, cursor, limit
        )

    @router.get("/asset-proposals/{proposal_id}")
    def asset_proposal(
        request: Request,
        proposal_id: Annotated[str, PathParam(min_length=1, max_length=36)],
        current: Authenticated,
    ) -> dict[str, Any]:
        return ProposalService(service(request).engine).get(current.user, proposal_id)

    @router.post("/asset-proposals/review")
    def review_asset_proposal(
        request: Request, body: ProposalReview, current: Mutation
    ) -> dict[str, Any]:
        return ProposalService(service(request).engine).review(current.user, body)

    @router.post("/asset-proposals/preview")
    def preview_asset_proposal(
        request: Request, body: ProposalPreview, current: Mutation
    ) -> dict[str, Any]:
        return ProposalService(service(request).engine).preview(current.user, body)

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

    @router.post("/conversations/{conversation_id}/deletion-preview")
    def deletion_preview(
        request: Request,
        conversation_id: Annotated[str, PathParam(min_length=1, max_length=36)],
        body: ConversationPreview,
        current: Mutation,
    ) -> dict[str, Any]:
        return ConversationPrivacy(service(request).engine).preview(
            current.user, conversation_id
        )

    @router.post("/conversations/{conversation_id}/stop-pending")
    def deletion_stop(
        request: Request,
        conversation_id: Annotated[str, PathParam(min_length=1, max_length=36)],
        body: ConversationToken,
        current: Mutation,
    ) -> dict[str, Any]:
        return ConversationPrivacy(service(request).engine).stop(
            current.user, conversation_id, body
        )

    @router.post("/conversations/{conversation_id}/delete")
    def deletion_apply(
        request: Request,
        conversation_id: Annotated[str, PathParam(min_length=1, max_length=36)],
        body: ConversationDelete,
        current: Mutation,
    ) -> dict[str, Any]:
        return ConversationPrivacy(service(request).engine).delete(
            current.user, conversation_id, body
        )

    async def run(
        request: Request,
        conversation_id: str,
        body: TurnInput,
        current: CurrentSession,
        emit: DeltaSink | None = None,
        begun: tuple[dict[str, Any], bool] | None = None,
    ) -> dict[str, Any]:
        chat = service(request)
        row, fresh = (
            begun
            if begun is not None
            else chat.begin(current.user, conversation_id, body)
        )
        if not fresh and not (body.mode == "scan_email" and row["state"] == "pending"):
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
                    request.app.state.claude_provider,
                    emit,
                    google_provider=request.app.state.google_provider,
                )

        if body.mode == "organize":
            try:
                active()
                organized = chat.organize(current.user, conversation_id, body)
                if organized is not None:
                    return organized
                return chat.finish(current.user, turn_id, {"text": HELP})
            except MemoryError as error:
                return chat.finish(
                    current.user, turn_id, {"text": str(error)}, "failed"
                )
            except asyncio.CancelledError:
                return chat.finish(
                    current.user, turn_id, {"text": "Request stopped."}, "canceled"
                )

        if body.mode == "scan_email":
            try:
                active()
                return chat.start_scan(
                    current.user, conversation_id, body, request.app.state.scan_service
                )
            except asyncio.CancelledError:
                return chat.finish(
                    current.user,
                    turn_id,
                    {"text": "Scan request stopped before enqueue."},
                    "canceled",
                )
            except Exception:
                return chat.finish(
                    current.user,
                    turn_id,
                    {
                        "text": (
                            "Scan was not queued. Check the mailbox connection, "
                            "scan scope and daily scan limit, then start a new request."
                        )
                    },
                    "failed",
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

    @router.post("/conversations/{conversation_id}/turns")
    async def send(
        request: Request, conversation_id: str, body: TurnInput, current: Mutation
    ) -> dict[str, Any]:
        return await run(request, conversation_id, body, current)

    @router.post("/conversations/{conversation_id}/stream")
    async def stream(
        request: Request, conversation_id: str, body: TurnInput, current: Mutation
    ) -> StreamingResponse:
        if body.mode != "ask":
            raise HTTPException(422, "Streaming is available for Ask AI")
        begun = service(request).begin(current.user, conversation_id, body)

        async def generate() -> AsyncIterator[bytes]:
            queue: asyncio.Queue[str] = asyncio.Queue(maxsize=8)

            async def emit(text: str) -> None:
                await queue.put(text)

            def event(value: dict[str, Any]) -> bytes:
                return (
                    "data: " + json.dumps(value, ensure_ascii=False) + "\n\n"
                ).encode()

            task = asyncio.create_task(
                run(request, conversation_id, body, current, emit, begun)
            )
            try:
                yield event({"type": "status", "text": "Finding supporting evidence…"})
                while not task.done():
                    try:
                        text = await asyncio.wait_for(queue.get(), timeout=0.25)
                        yield event({"type": "draft", "text": text})
                    except TimeoutError:
                        continue
                while not queue.empty():
                    yield event({"type": "draft", "text": queue.get_nowait()})
                yield event({"type": "complete", "turn": await task})
            finally:
                if begun[1]:
                    service(request).cancel(current.user, body.request_id)
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return router

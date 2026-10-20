"""Thin private source-library and graph adapters over shared domain services."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from lifegather.auth.routes import require_session, require_write_session
from lifegather.auth.store import CurrentSession
from lifegather.chat.service import SaveText, save_text
from lifegather.memory.library import LibraryPage, MemoryLibrary
from lifegather.memory.service import MemoryError, MemoryService

Authenticated = Annotated[CurrentSession, Depends(require_session)]


def library_router() -> APIRouter:
    router = APIRouter(prefix="/api/memories")

    @router.get("")
    def memories(
        request: Request,
        current: Authenticated,
        query: Annotated[str, Query(max_length=200)] = "",
        kind: Literal[
            "all", "notes", "photos", "pdfs", "documents", "emails", "other"
        ] = "all",
        include_history: bool = False,
        cursor: Annotated[str, Query(max_length=36)] = "",
        limit: Annotated[int, Query(ge=1, le=25)] = 25,
    ) -> dict[str, Any]:
        return MemoryLibrary(request.app.state.auth_store.engine).list(
            current.user,
            LibraryPage(
                query=query,
                kind=kind,
                include_history=include_history,
                cursor=cursor,
                limit=limit,
            ),
        )

    @router.post("", status_code=201)
    def capture(
        request: Request,
        body: SaveText,
        current: Annotated[CurrentSession, Depends(require_write_session)],
    ) -> dict[str, Any]:
        source = save_text(
            MemoryService(request.app.state.auth_store.engine), current.user, body
        )
        return source.model_dump(mode="json")

    return router


def graph_router() -> APIRouter:
    router = APIRouter(prefix="/api/graph")

    @router.get("/entities")
    def entities(
        request: Request,
        current: Authenticated,
        cursor: Annotated[str, Query(max_length=36)] = "",
        limit: Annotated[int, Query(ge=1, le=50)] = 25,
    ) -> dict[str, Any]:
        return MemoryService(request.app.state.auth_store.engine).list_entities(
            current.user, cursor, limit
        )

    @router.get("/{entity_id}")
    def graph(
        request: Request,
        current: Authenticated,
        entity_id: Annotated[str, Path(min_length=1, max_length=36)],
        depth: Annotated[int, Query(ge=1, le=2)] = 1,
        limit: Annotated[int, Query(ge=1, le=50)] = 25,
        fact_cursor: Annotated[str | None, Query(max_length=36)] = None,
    ) -> dict[str, Any]:
        memory = MemoryService(request.app.state.auth_store.engine)
        try:
            entity = memory.get_entity(current.user, entity_id)
        except MemoryError:
            raise HTTPException(404, "Entity not found") from None
        facts = memory.facts(current.user, entity_id, cursor=fact_cursor, limit=limit)
        return {
            "entity": entity,
            **memory.related(current.user, entity_id, depth=depth, limit=limit),
            "facts": facts,
            "next_fact_cursor": facts[-1].id if len(facts) == limit else None,
        }

    return router

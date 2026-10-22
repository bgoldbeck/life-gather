from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool

from lifegather.auth.routes import require_session, require_write_session
from lifegather.auth.store import CurrentSession
from lifegather.credentials.service import CredentialInput, PrivateSettings

Authenticated = Annotated[CurrentSession, Depends(require_session)]
Mutation = Annotated[CurrentSession, Depends(require_write_session)]


class PreferencesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allow_external_ai: StrictBool


class AppearanceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme: Literal["system", "light", "dark", "forest-dark"]


class ReplacementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    secret: SecretStr = Field(min_length=1, max_length=8192)


def service_for(request: Request) -> PrivateSettings:
    service: PrivateSettings = request.app.state.private_settings
    return service


def private_router() -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/appearance")
    def appearance(request: Request, current: Authenticated) -> dict[str, str]:
        return {"theme": service_for(request).theme(current.user)}

    @router.put("/appearance")
    def update_appearance(
        request: Request, body: AppearanceInput, current: Mutation
    ) -> Response:
        service_for(request).set_theme(current.user, body.theme)
        return Response(status_code=204)

    @router.get("/settings")
    def settings(request: Request, current: Authenticated) -> dict[str, bool]:
        service = service_for(request)
        return {
            "allow_external_ai": service.preferences(current.user),
            "vault_configured": service.enabled,
        }

    @router.put("/settings")
    def update_settings(
        request: Request, body: PreferencesInput, current: Mutation
    ) -> Response:
        service_for(request).set_preferences(current.user, body.allow_external_ai)
        return Response(status_code=204)

    @router.get("/credentials")
    def credentials(
        request: Request,
        current: Authenticated,
        cursor: Annotated[str, Query(max_length=36)] = "",
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ) -> JSONResponse:
        return JSONResponse(service_for(request).list(current.user, cursor, limit))

    @router.post("/credentials", status_code=201)
    def save(
        request: Request, body: CredentialInput, current: Mutation
    ) -> JSONResponse:
        entry = service_for(request).save(
            current.user,
            body.kind,
            body.provider,
            body.label,
            body.secret.get_secret_value(),
        )
        return JSONResponse(asdict(entry), status_code=201)

    @router.put("/credentials/{credential_id}")
    def replace(
        request: Request, credential_id: str, body: ReplacementInput, current: Mutation
    ) -> JSONResponse:
        return JSONResponse(
            asdict(
                service_for(request).replace(
                    current.user,
                    credential_id,
                    body.secret.get_secret_value(),
                )
            )
        )

    @router.delete("/credentials/{credential_id}")
    def remove(request: Request, credential_id: str, current: Mutation) -> Response:
        service_for(request).remove(current.user, credential_id)
        return Response(status_code=204)

    return router

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from lifegather.auth.deletion import AccountDeletion, AccountDeletionError
from lifegather.auth.email_routes import client_id, email_for
from lifegather.auth.routes import SESSION_COOKIE, require_write_session, store_for
from lifegather.auth.store import CurrentSession
from lifegather.config import Settings


class AccountDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=1, max_length=254)
    password: SecretStr | None = Field(default=None, max_length=128)


def account_router() -> APIRouter:
    router = APIRouter()

    @router.post("/api/account/delete")
    def delete_account(
        data: AccountDeleteInput,
        request: Request,
        current: Annotated[CurrentSession, Depends(require_write_session)],
    ) -> JSONResponse:
        settings: Settings = request.app.state.settings
        service = AccountDeletion(
            store_for(request).engine,
            request.app.state.object_storage,
            email_for(request),
        )
        try:
            result = service.delete(
                current.user,
                email=data.email,
                password=data.password.get_secret_value() if data.password else None,
                client=client_id(request),
                now=int(time.time()),
            )
        except AccountDeletionError as error:
            raise HTTPException(error.status, str(error)) from None
        response = JSONResponse(
            {"deleted": True, "rows": result.rows, "files": result.files}
        )
        response.delete_cookie(
            SESSION_COOKIE,
            path="/",
            secure=settings.secure_cookies,
            httponly=True,
            samesite="lax",
        )
        return response

    return router

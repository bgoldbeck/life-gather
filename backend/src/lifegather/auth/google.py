from typing import Any, cast

import httpx2
from authlib.integrations.base_client.errors import OAuthError  # type: ignore[import-untyped]
from authlib.integrations.starlette_client import OAuth  # type: ignore[import-untyped]
from joserfc.errors import JoseError
from pydantic import BaseModel, Field, ValidationError

from lifegather.config import Settings


class GoogleIdentity(BaseModel):
    sub: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=1, max_length=320)
    name: str = Field(default="", max_length=300)
    email_verified: bool


class GoogleFailure(ValueError):
    pass


class GoogleProvider:
    """Only Authlib-verified Google ID tokens can become account identities."""

    def __init__(
        self, settings: Settings, transport: httpx2.AsyncBaseTransport | None = None
    ) -> None:
        self.callback = settings.google_callback
        oauth = OAuth()
        client_kwargs: dict[str, Any] = {
            "scope": "openid email profile",
            "code_challenge_method": "S256",
            "timeout": 10,
        }
        if transport is not None:
            client_kwargs["transport"] = transport
        self.client: Any = oauth.register(
            "google",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret.get_secret_value(),
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs=client_kwargs,
        )

    async def authorization_url(self, state: str, nonce: str, verifier: str) -> str:
        try:
            result = await self.client.create_authorization_url(
                self.callback,
                state=state,
                nonce=nonce,
                code_verifier=verifier,
            )
            return cast(str, result["url"])
        except (OAuthError, httpx2.HTTPError, ValueError) as error:
            raise GoogleFailure("Google sign-in unavailable") from error

    async def exchange(self, code: str, nonce: str, verifier: str) -> GoogleIdentity:
        try:
            token = await self.client.fetch_access_token(
                redirect_uri=self.callback,
                code=code,
                code_verifier=verifier,
            )
            claims = await self.client.parse_id_token(
                token,
                nonce=nonce,
                leeway=30,
                claims_options={
                    "iss": {
                        "values": ["https://accounts.google.com", "accounts.google.com"]
                    }
                },
            )
            identity = GoogleIdentity.model_validate(dict(claims or {}))
            if not identity.email_verified:
                raise GoogleFailure("Google email is not verified")
            return identity
        except (
            OAuthError,
            JoseError,
            httpx2.HTTPError,
            ValidationError,
            ValueError,
        ) as error:
            raise GoogleFailure("Google sign-in failed") from error

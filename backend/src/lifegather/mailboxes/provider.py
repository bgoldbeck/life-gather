"""Fixed read-only Gmail OAuth endpoints; no message mutation or model tools."""

import base64
import hashlib
import re
from typing import Any
from urllib.parse import urlencode

import httpx2
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from lifegather.config import Settings

READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_URL = "https://gmail.googleapis.com/gmail/v1/users/me"


class MailboxFailure(ValueError):
    pass


class GmailGrant(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    address: str = Field(min_length=3, max_length=320)
    refresh_token: SecretStr = Field(min_length=1, max_length=4096, repr=False)

    @field_validator("address")
    @classmethod
    def valid_address(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,255}", value):
            raise ValueError("Invalid mailbox address")
        return value


class GmailProvider:
    def __init__(
        self, settings: Settings, transport: httpx2.AsyncBaseTransport | None = None
    ) -> None:
        self.client_id = settings.google_client_id
        self.secret = settings.google_client_secret.get_secret_value()
        self.callback = settings.public_url + "/auth/gmail/callback"
        self.transport = transport

    def authorization_url(self, state: str, verifier: str) -> str:
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.callback,
                "response_type": "code",
                "scope": READ_SCOPE,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "access_type": "offline",
                "prompt": "consent select_account",
                "include_granted_scopes": "false",
            }
        )

    async def request(
        self,
        method: str,
        url: str,
        *,
        form: dict[str, str] | None = None,
        token: str = "",
        params: dict[str, str | int] | None = None,
    ) -> dict[str, Any]:
        if not (url == TOKEN_URL or url == GMAIL_URL + "/profile"):
            raise MailboxFailure("Unsupported mailbox operation")
        try:
            async with httpx2.AsyncClient(
                transport=self.transport,
                timeout=10,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                async with client.stream(
                    method,
                    url,
                    data=form,
                    params=params,
                    headers={"Authorization": "Bearer " + token} if token else {},
                ) as response:
                    if response.status_code != 200:
                        raise ValueError("Mailbox request failed")
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(data) + len(chunk) > 524288:
                            raise ValueError("Mailbox response too large")
                        data.extend(chunk)
                    import json

                    value = json.loads(data)
                    if not isinstance(value, dict):
                        raise ValueError("Invalid mailbox response")
                    return value
        except (httpx2.HTTPError, ValueError, TypeError):
            raise MailboxFailure(
                "Mailbox request failed. Reconnect and try again."
            ) from None

    @staticmethod
    def access_value(value: dict[str, Any]) -> str:
        token = value.get("access_token")
        if (
            not isinstance(token, str)
            or not token
            or len(token) > 8192
            or not re.fullmatch(r"[A-Za-z0-9._~+/-]+={0,2}", token)
        ):
            raise MailboxFailure("Mailbox authorization did not provide access")
        return token

    async def exchange(self, code: str, verifier: str) -> GmailGrant:
        try:
            value = await self.request(
                "POST",
                TOKEN_URL,
                form={
                    "client_id": self.client_id,
                    "client_secret": self.secret,
                    "redirect_uri": self.callback,
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": verifier,
                },
            )
            if READ_SCOPE not in str(value.get("scope", "")).split():
                raise ValueError("Read-only permission missing")
            token = self.access_value(value)
            refresh = value.get("refresh_token")
            profile = await self.request("GET", GMAIL_URL + "/profile", token=token)
            return GmailGrant.model_validate(
                {"address": profile.get("emailAddress"), "refresh_token": refresh}
            )
        except (ValueError, TypeError):
            raise MailboxFailure(
                "Mailbox connection failed. Grant read-only access and reconnect."
            ) from None

    async def access(self, refresh_token: str) -> str:
        value = await self.request(
            "POST",
            TOKEN_URL,
            form={
                "client_id": self.client_id,
                "client_secret": self.secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        return self.access_value(value)

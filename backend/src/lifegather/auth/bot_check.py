"""Optional Cloudflare Turnstile verification for public account forms."""

import logging
from typing import Protocol

import httpx2
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

SITEVERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class BotCheck(Protocol):
    def verify(self, token: str, remote_ip: str) -> bool: ...


class SiteVerify(BaseModel):
    success: bool


class TurnstileCheck:
    """Fails closed: a missing token or unreachable Cloudflare is not a pass."""

    def __init__(
        self, secret: str, transport: httpx2.BaseTransport | None = None
    ) -> None:
        self.secret, self.transport = secret, transport

    def verify(self, token: str, remote_ip: str) -> bool:
        if not token or len(token) > 2048:
            return False
        try:
            with httpx2.Client(transport=self.transport, timeout=10) as client:
                response = client.post(
                    SITEVERIFY,
                    data={
                        "secret": self.secret,
                        "response": token,
                        "remoteip": remote_ip,
                    },
                )
            response.raise_for_status()
            return SiteVerify.model_validate_json(response.content).success
        except (httpx2.HTTPError, ValidationError):
            logger.warning("Turnstile verification unavailable; request refused")
            return False

import re


class EmailAuthError(ValueError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def email_key(value: str) -> str:
    value = value.strip()
    if len(value) > 254 or value.count("@") != 1 or not value.isascii():
        raise EmailAuthError("Enter a valid email address")
    local, domain = value.split("@")
    if (
        not 1 <= len(local) <= 64
        or not re.fullmatch(r"[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+", local)
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
    ):
        raise EmailAuthError("Enter a valid email address")
    labels = domain.split(".")
    if len(labels) < 2 or any(
        not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
        for label in labels
    ):
        raise EmailAuthError("Enter a valid email address")
    return value.casefold()


def password_value(value: str) -> str:
    if not 15 <= len(value) <= 128 or len(value.encode("utf-8")) > 512:
        raise EmailAuthError("Use a password between 15 and 128 characters")
    if value.casefold() in {
        "passwordpassword",
        "123456789012345",
        "1234567890123456",
        "qwertyuiopasdfgh",
        "letmeinletmeinletmein",
    }:
        raise EmailAuthError("Choose a less common password")
    return value

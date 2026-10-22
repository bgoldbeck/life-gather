from sqlalchemy import CheckConstraint, ForeignKey, Index, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


class VaultKey(Base):
    __tablename__ = "vault_key"
    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str]


class UserSettings(Base):
    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint(
            "theme IN ('system','light','dark','forest-dark')", name="ck_user_theme"
        ),
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    allow_external_ai: Mapped[bool]
    theme: Mapped[str] = mapped_column(server_default="system")
    conversation_retention_days: Mapped[int | None] = mapped_column(
        CheckConstraint(
            "conversation_retention_days IS NULL "
            "OR conversation_retention_days IN (30, 90, 365)",
            name="ck_user_conversation_retention",
        )
    )


class Credential(Base):
    __tablename__ = "credentials"
    __table_args__ = (Index("uq_credentials_user_id_id", "user_id", "id", unique=True),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str]
    provider: Mapped[str]
    label: Mapped[str]
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[int]
    updated_at: Mapped[int]

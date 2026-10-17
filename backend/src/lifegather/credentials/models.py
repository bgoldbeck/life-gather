from sqlalchemy import ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


class VaultKey(Base):
    __tablename__ = "vault_key"
    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str]


class UserSettings(Base):
    __tablename__ = "user_settings"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    allow_external_ai: Mapped[bool]


class Credential(Base):
    __tablename__ = "credentials"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str]
    provider: Mapped[str]
    label: Mapped[str]
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[int]
    updated_at: Mapped[int]

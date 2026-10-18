from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


class ExternalIdentity(Base):
    __tablename__ = "external_identities"
    __table_args__ = (UniqueConstraint("issuer", "subject"),)
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    issuer: Mapped[str]
    subject: Mapped[str]


class EmailCredential(Base):
    __tablename__ = "email_credentials"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    email_key: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    generation: Mapped[str]
    verified_at: Mapped[int]


class EmailChallenge(Base):
    __tablename__ = "email_challenges"
    __table_args__ = (CheckConstraint("purpose IN ('signup','link','reset')"),)
    token_hash: Mapped[str] = mapped_column(primary_key=True)
    purpose: Mapped[str]
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    email_key: Mapped[str] = mapped_column(index=True)
    name: Mapped[str]
    generation: Mapped[str | None]
    expires_at: Mapped[int] = mapped_column(index=True)
    created_at: Mapped[int]
    consumed_at: Mapped[int | None]


class AuthAttempt(Base):
    __tablename__ = "auth_attempts"
    key: Mapped[str] = mapped_column(primary_key=True)
    count: Mapped[int]
    expires_at: Mapped[int] = mapped_column(index=True)

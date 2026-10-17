from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_google_identity"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    issuer: Mapped[str]
    subject: Mapped[str]
    email: Mapped[str]
    name: Mapped[str]
    created_at: Mapped[int]


class LoginFlow(Base):
    __tablename__ = "login_flows"
    browser_hash: Mapped[str] = mapped_column(String, primary_key=True)
    state_hash: Mapped[str]
    nonce: Mapped[str]
    verifier: Mapped[str]
    expires_at: Mapped[int] = mapped_column(index=True)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    csrf_token: Mapped[str]
    expires_at: Mapped[int] = mapped_column(index=True)

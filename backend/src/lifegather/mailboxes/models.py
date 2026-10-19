from sqlalchemy import ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


class Mailbox(Base):
    __tablename__ = "mailboxes"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "account_key"),
        ForeignKeyConstraint(
            ["user_id", "credential_id"], ["credentials.user_id", "credentials.id"]
        ),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    credential_id: Mapped[str | None] = mapped_column(
        ForeignKey("credentials.id", ondelete="SET NULL")
    )
    account_key: Mapped[str]
    address: Mapped[str]
    revision: Mapped[int]
    created_at: Mapped[int]
    updated_at: Mapped[int]


class MailboxFlow(Base):
    __tablename__ = "mailbox_oauth_flows"
    state_hash: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    session_hash: Mapped[str]
    browser_hash: Mapped[str]
    verifier: Mapped[str]
    expires_at: Mapped[int] = mapped_column(index=True)

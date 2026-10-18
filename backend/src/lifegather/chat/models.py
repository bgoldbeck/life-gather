from sqlalchemy import ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


class Conversation(Base):
    __tablename__ = "chat_conversations"
    __table_args__ = (UniqueConstraint("user_id", "id"),)
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str]
    created_at: Mapped[int]


class Turn(Base):
    __tablename__ = "chat_turns"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id"),
        ForeignKeyConstraint(
            ["user_id", "conversation_id"],
            ["chat_conversations.user_id", "chat_conversations.id"],
        ),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(index=True)
    request_id: Mapped[str]
    mode: Mapped[str]
    text: Mapped[str]
    fingerprint: Mapped[str]
    state: Mapped[str]
    result_json: Mapped[str]
    created_at: Mapped[int]


class Usage(Base):
    __tablename__ = "chat_usage"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    day: Mapped[str] = mapped_column(primary_key=True)
    requests: Mapped[int]
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]

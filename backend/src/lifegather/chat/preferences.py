"""Remember explicit choices without implying permission to contact a provider."""

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Engine, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.chat.models import ChatPreference
from lifegather.credentials.models import Credential
from lifegather.credentials.service import PrivateSettings, VaultError


class ChatChoice(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )
    credential_id: str = Field(default="", max_length=36)
    model: str = Field(default="", max_length=100, pattern=r"^[a-zA-Z0-9._:-]*$")

    @model_validator(mode="after")
    def complete_choice(self) -> "ChatChoice":
        if bool(self.credential_id) != bool(self.model):
            raise ValueError("Choose both a connection and model, or clear both")
        return self


class ChatPreferences:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def get(self, actor: Account) -> ChatChoice:
        with Session(self.engine) as db:
            choice = db.get(ChatPreference, actor.id)
            if choice is None or choice.credential_id is None:
                return ChatChoice()
            credential = db.scalar(
                select(Credential)
                .where(
                    Credential.user_id == actor.id,
                    Credential.id == choice.credential_id,
                    Credential.kind == "ai",
                    Credential.provider.in_(["openai", "anthropic"]),
                )
                .limit(1)
            )
            if credential is None:
                return ChatChoice()
            return ChatChoice(credential_id=credential.id, model=choice.model)

    def set(self, actor: Account, value: ChatChoice) -> None:
        data = ChatChoice.model_validate(value)
        with Session(self.engine) as db, db.begin():
            if data.credential_id:
                credential = PrivateSettings._owned(db, actor, data.credential_id)
                if credential.kind != "ai" or credential.provider not in {
                    "openai",
                    "anthropic",
                }:
                    raise VaultError("Choose a supported AI connection", 422)
            values = {"credential_id": data.credential_id or None, "model": data.model}
            db.execute(
                insert(ChatPreference)
                .values(user_id=actor.id, **values)
                .on_conflict_do_update(index_elements=["user_id"], set_=values)
            )

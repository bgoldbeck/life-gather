"""Owner-scoped word index for sources and entity names.

Terms are Unicode words, case-folded with diacritics removed, stored as a text
array with a GIN index. A query matches records that contain every query word.
"""

import re
import unicodedata

from sqlalchemy import (
    Column,
    ColumnElement,
    String,
    Table,
    Text,
    and_,
    delete,
    false,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session

from lifegather.auth.models import Base

WORD = re.compile(r"[^\W_]+", re.UNICODE)

search_index = Table(
    "memory_fts",
    Base.metadata,
    Column("record_id", String, nullable=False),
    Column("user_id", String, nullable=False),
    Column("kind", String, nullable=False),
    Column("body", String, nullable=False),
    Column("terms", ARRAY(Text), nullable=False),
)


def fold(word: str) -> str:
    decomposed = unicodedata.normalize("NFKD", word.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def query_words(query: str) -> list[str]:
    return WORD.findall(query)


def terms(body: str) -> list[str]:
    return sorted({fold(word) for word in WORD.findall(body)} - {""})


def index_record(
    db: Session, owner: str, identifier: str, kind: str, body: str
) -> None:
    db.execute(
        delete(search_index).where(
            search_index.c.user_id == owner,
            search_index.c.record_id == identifier,
            search_index.c.kind == kind,
        )
    )
    db.execute(
        search_index.insert().values(
            record_id=identifier,
            user_id=owner,
            kind=kind,
            body=body,
            terms=terms(body),
        )
    )


def matches_words(owner: str, words: list[str]) -> ColumnElement[bool]:
    folded = sorted({fold(word) for word in words} - {""})
    if not folded:
        return false()
    return and_(
        search_index.c.user_id == owner,
        search_index.c.terms.contains(folded),
    )

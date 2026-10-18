from pydantic import BaseModel, ConfigDict, Field

from lifegather.assets.actions import AssetChange
from lifegather.assets.service import AssetList, AssetRead
from lifegather.chat.service import SaveText
from lifegather.documents.service import DocumentPage, DocumentRead
from lifegather.memory.library import LibraryPage
from lifegather.memory.notes import CorrectionInput, NoteHistoryInput
from lifegather.photos.service import PhotoList, PhotoRead
from lifegather.profiles.service import ProfileRead
from lifegather.reconciliation.proposals import (
    ProposalPreview,
    ProposalRead,
    ProposalReview,
)
from lifegather.reconciliation.purchase_details import DetailRead, DetailSave
from lifegather.reconciliation.queue import IdentityRead, IdentityReview, ReviewPage
from lifegather.reconciliation.receipts import (
    ReceiptPreview,
    ReceiptRead,
    ReceiptReview,
)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Page(Input):
    cursor: str = Field(default="", max_length=36)
    limit: int = Field(default=25, ge=1, le=50)


class Search(Input):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=25, ge=1, le=50)


class EntityFind(Input):
    name: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=3, ge=1, le=5)


class EntityRead(Input):
    entity_id: str = Field(min_length=1, max_length=36)
    cursor: str | None = Field(default=None, max_length=36)
    limit: int = Field(default=25, ge=1, le=50)
    world_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    known_at: int | None = Field(default=None, ge=0, le=9223372036854775807)


class SourceRead(Input):
    source_id: str = Field(min_length=1, max_length=36)
    offset: int = Field(default=0, ge=0, le=20000)
    limit: int = Field(default=4000, ge=1, le=4000)


class GraphRead(Input):
    entity_id: str = Field(min_length=1, max_length=36)
    depth: int = Field(default=1, ge=1, le=2)
    limit: int = Field(default=25, ge=1, le=50)


class HistoryRead(Page):
    entity_id: str = Field(min_length=1, max_length=36)


class DiscoveryRead(Input):
    observation_id: str = Field(min_length=1, max_length=36)


class DiscoveryHistory(Page):
    observation_id: str = Field(min_length=1, max_length=36)


INPUTS: dict[str, type[BaseModel]] = {
    "receipt_get": ReceiptRead,
    "receipt_details_get": DetailRead,
    "receipt_details_save": DetailSave,
    "receipt_preview": ReceiptPreview,
    "receipt_review": ReceiptReview,
    "memory_library": LibraryPage,
    "document_list": DocumentPage,
    "document_get": DocumentRead,
    "profile_get": ProfileRead,
    "review_queue": ReviewPage,
    "review_identity": IdentityRead,
    "review_identity_resolve": IdentityReview,
    "asset_change": AssetChange,
    "assets_list": AssetList,
    "asset_detail": AssetRead,
    "asset_proposal_preview": ProposalPreview,
    "asset_proposal_get": ProposalRead,
    "asset_proposal_review": ProposalReview,
    "memory_correct_note": CorrectionInput,
    "memory_note_history": NoteHistoryInput,
    "memory_save_text": SaveText,
    "memory_search": Search,
    "memory_find_entities": EntityFind,
    "memory_get_entity": EntityRead,
    "memory_source": SourceRead,
    "memory_related": GraphRead,
    "memory_timeline": HistoryRead,
    "memory_list_entities": Page,
    "discovery_get": DiscoveryRead,
    "discovery_reviews": Page,
    "discovery_inventory": Page,
    "discovery_history": DiscoveryHistory,
}

INPUTS["photo_list"] = PhotoList
INPUTS["photo_get"] = PhotoRead

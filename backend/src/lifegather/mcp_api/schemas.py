from pydantic import BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Page(Input):
    cursor: str = Field(default="", max_length=36)
    limit: int = Field(default=25, ge=1, le=50)


class Search(Input):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=25, ge=1, le=50)


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


INPUTS: dict[str, type[Input]] = {
    "memory_search": Search,
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

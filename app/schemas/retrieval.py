from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


MAX_KNOWLEDGE_SEARCH_QUERY_CHARS = 2_000


class KnowledgeSearchRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    query: str = Field(
        min_length=1,
        max_length=MAX_KNOWLEDGE_SEARCH_QUERY_CHARS,
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
    )
    min_similarity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )

    @field_validator("query", mode="before")
    @classmethod
    def validate_raw_query_length(
        cls,
        value: object,
    ) -> object:
        if (
            isinstance(value, str)
            and len(value)
            > MAX_KNOWLEDGE_SEARCH_QUERY_CHARS
        ):
            raise ValueError(
                "Knowledge search query exceeds maximum length"
            )

        return value


class KnowledgeSearchResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    chunk_id: UUID
    document_id: UUID
    document_title: str
    source_type: str
    source_name: str
    chunk_index: int
    content: str
    similarity: float


class KnowledgeSearchResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    results: list[KnowledgeSearchResult]
    result_count: int
    embedding_model: str
    embedding_dimensions: int
    token_usage: int

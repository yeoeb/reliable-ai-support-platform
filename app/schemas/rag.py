from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.retrieval import MAX_KNOWLEDGE_SEARCH_QUERY_CHARS


class RagAnswerRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    question: str = Field(
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

    @field_validator("question", mode="before")
    @classmethod
    def validate_raw_question_length(
        cls,
        value: object,
    ) -> object:
        if (
            isinstance(value, str)
            and len(value) > MAX_KNOWLEDGE_SEARCH_QUERY_CHARS
        ):
            raise ValueError(
                "RAG question exceeds maximum length"
            )
        return value


class RagCitation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    source_id: str
    chunk_id: UUID
    document_id: UUID
    document_title: str
    source_type: str
    source_name: str
    chunk_index: int
    similarity: float
    content: str


class RagAnswerResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    status: Literal["grounded", "insufficient_evidence"]
    answer: str
    citations: list[RagCitation]
    generation_model: str | None
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)

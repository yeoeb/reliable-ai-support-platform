from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


MAX_KNOWLEDGE_CONTENT_CHARS = 100_000


class KnowledgeDocumentCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    title: str = Field(
        min_length=1,
        max_length=200,
    )
    source_type: Literal["text", "markdown"]
    source_name: str = Field(
        min_length=1,
        max_length=255,
    )
    content: str = Field(
        min_length=1,
        max_length=MAX_KNOWLEDGE_CONTENT_CHARS,
    )

    @field_validator("content", mode="before")
    @classmethod
    def validate_raw_content_length(
        cls,
        value: object,
    ) -> object:
        if (
            isinstance(value, str)
            and len(value)
            > MAX_KNOWLEDGE_CONTENT_CHARS
        ):
            raise ValueError(
                "Knowledge content exceeds maximum length"
            )

        return value


class KnowledgeDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    source_type: str
    source_name: str
    content_hash: str
    created_at: datetime
    changed: bool

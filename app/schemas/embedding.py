from uuid import UUID

from pydantic import BaseModel, ConfigDict


class KnowledgeEmbeddingRead(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    document_id: UUID
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    chunk_count: int
    embedding_config_hash: str
    changed: bool
    token_usage: int

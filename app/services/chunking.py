from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256


CHUNKING_STRATEGY = "char-v1"
@dataclass(frozen=True)
class TextChunk:
    index: int
    content: str
    content_hash: str


@dataclass(frozen=True)
class EmbeddingPipelineConfig:
    provider_name: str
    chunking_strategy: str
    chunk_size: int
    chunk_overlap: int
    embedding_model: str
    embedding_dimensions: int

    @property
    def config_hash(self) -> str:
        payload = {
            "provider_name": self.provider_name,
            "chunking_strategy": self.chunking_strategy,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "embedding_model": self.embedding_model,
            "embedding_dimensions": self.embedding_dimensions,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return sha256(encoded).hexdigest()


def hash_chunk(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def split_into_chunks(
    content: str,
    *,
    chunk_size: int,
    overlap: int,
) -> list[TextChunk]:
    if not content:
        raise ValueError("Knowledge content must not be empty")

    if not 1 <= chunk_size <= 2000:
        raise ValueError(
            "chunk_size must be between 1 and 2000"
        )

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "overlap must be non-negative and smaller than chunk_size"
        )

    chunks: list[TextChunk] = []
    step = chunk_size - overlap
    start = 0
    index = 0

    while start < len(content):
        chunk_content = content[
            start : start + chunk_size
        ]

        if not chunk_content:
            break

        chunks.append(
            TextChunk(
                index=index,
                content=chunk_content,
                content_hash=hash_chunk(chunk_content),
            )
        )

        if start + chunk_size >= len(content):
            break

        start += step
        index += 1

    return chunks


def build_embedding_pipeline_config(
    *,
    provider_name: str,
    chunk_size: int,
    chunk_overlap: int,
    embedding_model: str,
    embedding_dimensions: int,
) -> EmbeddingPipelineConfig:
    return EmbeddingPipelineConfig(
        provider_name=provider_name,
        chunking_strategy=CHUNKING_STRATEGY,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
    )

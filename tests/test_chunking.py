import pytest

from app.services.chunking import (
    CHUNKING_STRATEGY,
    build_embedding_pipeline_config,
    hash_chunk,
    split_into_chunks,
)


def test_chunking_is_deterministic_with_overlap() -> None:
    content = "abcdefghij"

    chunks = split_into_chunks(
        content,
        chunk_size=4,
        overlap=1,
    )

    assert [
        chunk.content
        for chunk in chunks
    ] == [
        "abcd",
        "defg",
        "ghij",
    ]
    assert [
        chunk.index
        for chunk in chunks
    ] == [0, 1, 2]
    assert [
        chunk.content_hash
        for chunk in chunks
    ] == [
        hash_chunk("abcd"),
        hash_chunk("defg"),
        hash_chunk("ghij"),
    ]


def test_chunking_preserves_exact_characters() -> None:
    content = "  alpha\nbeta  "

    chunks = split_into_chunks(
        content,
        chunk_size=100,
        overlap=0,
    )

    assert len(chunks) == 1
    assert chunks[0].content == content


def test_chunking_never_exceeds_configured_size() -> None:
    chunks = split_into_chunks(
        "x" * 5000,
        chunk_size=2000,
        overlap=150,
    )

    assert chunks
    assert all(
        1 <= len(chunk.content) <= 2000
        for chunk in chunks
    )


@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [
        (0, 0),
        (2001, 0),
        (100, -1),
        (100, 100),
        (100, 101),
    ],
)
def test_chunking_rejects_invalid_configuration(
    chunk_size: int,
    overlap: int,
) -> None:
    with pytest.raises(ValueError):
        split_into_chunks(
            "content",
            chunk_size=chunk_size,
            overlap=overlap,
        )


def test_chunking_rejects_empty_content() -> None:
    with pytest.raises(ValueError):
        split_into_chunks(
            "",
            chunk_size=1000,
            overlap=150,
        )


def test_embedding_config_hash_is_deterministic() -> None:
    first = build_embedding_pipeline_config(
        provider_name="openai",
        chunk_size=1000,
        chunk_overlap=150,
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
    )
    second = build_embedding_pipeline_config(
        provider_name="openai",
        chunk_size=1000,
        chunk_overlap=150,
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
    )

    assert first.chunking_strategy == CHUNKING_STRATEGY
    assert first.config_hash == second.config_hash
    assert len(first.config_hash) == 64


def test_embedding_config_hash_changes_with_semantics() -> None:
    base = build_embedding_pipeline_config(
        provider_name="openai",
        chunk_size=1000,
        chunk_overlap=150,
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
    )

    changed = build_embedding_pipeline_config(
        provider_name="openai",
        chunk_size=900,
        chunk_overlap=150,
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
    )

    assert base.config_hash != changed.config_hash

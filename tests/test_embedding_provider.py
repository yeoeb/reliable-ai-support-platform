from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.errors import (
    EmbeddingProviderNotConfiguredError,
    InvalidEmbeddingProviderResponseError,
)
from app.integrations.embeddings import (
    OpenAIEmbeddingProvider,
)


DIMENSIONS = 1536


def make_item(
    index: int,
    *,
    dimensions: int = DIMENSIONS,
    value: float = 0.25,
):
    return SimpleNamespace(
        index=index,
        embedding=[value] * dimensions,
    )


def make_response(
    items,
    *,
    token_usage: int = 17,
):
    return SimpleNamespace(
        data=items,
        usage=SimpleNamespace(
            total_tokens=token_usage,
        ),
    )


def make_client(response):
    client = MagicMock()
    client.embeddings.create.return_value = response
    return client


def test_openai_provider_uses_explicit_model_and_dimensions() -> None:
    client = make_client(
        make_response(
            [
                make_item(0),
                make_item(1),
            ],
            token_usage=23,
        )
    )
    provider = OpenAIEmbeddingProvider(
        api_key=None,
        model="text-embedding-3-small",
        dimensions=DIMENSIONS,
        client=client,
    )

    result = provider.embed(
        ["first", "second"]
    )

    client.embeddings.create.assert_called_once_with(
        model="text-embedding-3-small",
        input=["first", "second"],
        dimensions=1536,
        encoding_format="float",
    )
    assert len(result.vectors) == 2
    assert len(result.vectors[0]) == DIMENSIONS
    assert result.token_usage == 23


def test_openai_provider_restores_index_order() -> None:
    client = make_client(
        make_response(
            [
                make_item(1, value=0.2),
                make_item(0, value=0.1),
            ]
        )
    )
    provider = OpenAIEmbeddingProvider(
        api_key=None,
        model="text-embedding-3-small",
        dimensions=DIMENSIONS,
        client=client,
    )

    result = provider.embed(
        ["first", "second"]
    )

    assert result.vectors[0][0] == 0.1
    assert result.vectors[1][0] == 0.2


def test_missing_api_key_fails_only_when_provider_is_used() -> None:
    provider = OpenAIEmbeddingProvider(
        api_key=None,
        model="text-embedding-3-small",
        dimensions=DIMENSIONS,
    )

    with pytest.raises(
        EmbeddingProviderNotConfiguredError,
    ):
        provider.embed(["text"])


def test_provider_rejects_empty_batch() -> None:
    provider = OpenAIEmbeddingProvider(
        api_key=None,
        model="text-embedding-3-small",
        dimensions=DIMENSIONS,
        client=MagicMock(),
    )

    with pytest.raises(ValueError):
        provider.embed([])


@pytest.mark.parametrize(
    "items",
    [
        [],
        [make_item(0, dimensions=12)],
        [make_item(1)],
    ],
)
def test_provider_rejects_malformed_response(
    items,
) -> None:
    provider = OpenAIEmbeddingProvider(
        api_key=None,
        model="text-embedding-3-small",
        dimensions=DIMENSIONS,
        client=make_client(
            make_response(items)
        ),
    )

    with pytest.raises(
        InvalidEmbeddingProviderResponseError,
    ):
        provider.embed(["text"])


@pytest.mark.parametrize(
    "bad_value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_provider_rejects_non_finite_vectors(
    bad_value: float,
) -> None:
    provider = OpenAIEmbeddingProvider(
        api_key=None,
        model="text-embedding-3-small",
        dimensions=DIMENSIONS,
        client=make_client(
            make_response(
                [
                    make_item(
                        0,
                        value=bad_value,
                    )
                ]
            )
        ),
    )

    with pytest.raises(
        InvalidEmbeddingProviderResponseError,
    ):
        provider.embed(["text"])



@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(
            usage=SimpleNamespace(total_tokens=1),
        ),
        SimpleNamespace(
            data=[make_item(0)],
        ),
        SimpleNamespace(
            data=[
                SimpleNamespace(
                    embedding=[0.1] * DIMENSIONS,
                )
            ],
            usage=SimpleNamespace(total_tokens=1),
        ),
        SimpleNamespace(
            data=[
                SimpleNamespace(
                    index=0,
                )
            ],
            usage=SimpleNamespace(total_tokens=1),
        ),
    ],
)
def test_provider_rejects_missing_response_fields(
    response,
) -> None:
    provider = OpenAIEmbeddingProvider(
        api_key=None,
        model="text-embedding-3-small",
        dimensions=DIMENSIONS,
        client=make_client(response),
    )

    with pytest.raises(
        InvalidEmbeddingProviderResponseError,
    ):
        provider.embed(["text"])


def test_provider_rejects_non_numeric_vector_value() -> None:
    response = make_response(
        [
            SimpleNamespace(
                index=0,
                embedding=[
                    "not-a-number"
                ] * DIMENSIONS,
            )
        ]
    )
    provider = OpenAIEmbeddingProvider(
        api_key=None,
        model="text-embedding-3-small",
        dimensions=DIMENSIONS,
        client=make_client(response),
    )

    with pytest.raises(
        InvalidEmbeddingProviderResponseError,
    ):
        provider.embed(["text"])


@pytest.mark.parametrize(
    "bad_usage",
    [
        None,
        "not-an-integer",
        -1,
    ],
)
def test_provider_rejects_invalid_token_usage(
    bad_usage,
) -> None:
    response = make_response(
        [make_item(0)]
    )
    response.usage.total_tokens = bad_usage

    provider = OpenAIEmbeddingProvider(
        api_key=None,
        model="text-embedding-3-small",
        dimensions=DIMENSIONS,
        client=make_client(response),
    )

    with pytest.raises(
        InvalidEmbeddingProviderResponseError,
    ):
        provider.embed(["text"])

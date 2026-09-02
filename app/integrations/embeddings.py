from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

from openai import OpenAI, OpenAIError

from app.core.errors import (
    EmbeddingProviderNotConfiguredError,
    EmbeddingProviderUnavailableError,
    InvalidEmbeddingProviderResponseError,
)


@dataclass(frozen=True)
class EmbeddingBatchResult:
    vectors: list[list[float]]
    token_usage: int


class EmbeddingProvider(Protocol):
    provider_name: str

    def embed(
        self,
        texts: list[str],
    ) -> EmbeddingBatchResult:
        ...


class OpenAIEmbeddingProvider:
    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        dimensions: int,
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key.strip() if api_key else None
        self.model = model
        self.dimensions = dimensions
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        if not self.api_key:
            raise EmbeddingProviderNotConfiguredError(
                "OpenAI API key is not configured"
            )

        self._client = OpenAI(
            api_key=self.api_key,
        )
        return self._client

    def embed(
        self,
        texts: list[str],
    ) -> EmbeddingBatchResult:
        if not texts:
            raise ValueError(
                "Embedding batch must not be empty"
            )

        client = self._get_client()

        try:
            response = client.embeddings.create(
                model=self.model,
                input=texts,
                dimensions=self.dimensions,
                encoding_format="float",
            )
        except OpenAIError as exc:
            raise EmbeddingProviderUnavailableError(
                "Embedding provider request failed"
            ) from exc

        data = list(response.data)

        if len(data) != len(texts):
            raise InvalidEmbeddingProviderResponseError(
                "Embedding provider returned an unexpected item count"
            )

        ordered = sorted(
            data,
            key=lambda item: item.index,
        )

        if [
            item.index
            for item in ordered
        ] != list(range(len(texts))):
            raise InvalidEmbeddingProviderResponseError(
                "Embedding provider returned invalid indexes"
            )

        vectors: list[list[float]] = []

        for item in ordered:
            raw_vector = list(item.embedding)

            if len(raw_vector) != self.dimensions:
                raise InvalidEmbeddingProviderResponseError(
                    "Embedding provider returned an invalid dimension"
                )

            vector = [
                float(value)
                for value in raw_vector
            ]

            if not all(
                math.isfinite(value)
                for value in vector
            ):
                raise InvalidEmbeddingProviderResponseError(
                    "Embedding provider returned a non-finite value"
                )

            vectors.append(vector)

        token_usage = int(
            getattr(
                response.usage,
                "total_tokens",
                0,
            )
            or 0
        )

        if token_usage < 0:
            raise InvalidEmbeddingProviderResponseError(
                "Embedding provider returned invalid token usage"
            )

        return EmbeddingBatchResult(
            vectors=vectors,
            token_usage=token_usage,
        )

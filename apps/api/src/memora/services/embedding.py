"""Embeddings behind a protocol, so tests never touch the network."""

from __future__ import annotations

import math
from typing import Protocol

from memora.config import get_settings


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else vector


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class GeminiEmbedder:
    def __init__(self, api_key: str, model: str, dims: int) -> None:
        self._api_key = api_key
        self._model = model
        self._dims = dims
        self._client = None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        from google import genai
        from google.genai import types

        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)

        response = await self._client.aio.models.embed_content(
            model=self._model,
            contents=texts,
            # This model defaults to 3072. The column is vector(768), so the size is
            # requested rather than assumed - a mismatch here is an insert failure.
            config=types.EmbedContentConfig(output_dimensionality=self._dims),
        )
        # Truncated dimensions come back un-normalized; cosine distance needs unit length.
        return [_unit(list(e.values)) for e in response.embeddings]


def build_embedder() -> Embedder:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set. Embedding is unavailable.")
    return GeminiEmbedder(
        api_key=settings.gemini_api_key,
        model=settings.embedding_model,
        dims=settings.embedding_dims,
    )

"""Embeddings behind a protocol, so tests never touch the network.

Every implementation takes ``MaskedText`` rather than ``str``. That is the enforcement
point for PRODUCT.md architectural rule 2: there is no ordering of calls that sends raw
extracted text to a hosted API, because the only way to obtain a MaskedText is to call
mask_identifiers().
"""

from __future__ import annotations

import math
from typing import Protocol

from memora.config import get_settings
from memora.services.masking import MaskedText, contains_identifier


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else vector


class Embedder(Protocol):
    async def embed(self, texts: list[MaskedText]) -> list[list[float]]: ...


def require_masked(texts: list[MaskedText]) -> list[str]:
    """The last gate before text leaves the machine.

    Two checks, and the second is the one that matters. The type check catches the
    ordinary mistake of passing a raw string. The content check catches every way of
    forging a MaskedText - ``object.__new__``, ``dataclasses.replace``, subclassing,
    an imported token - because it inspects the text rather than trusting how the
    object was built.

    Provenance can always be faked in Python. Content cannot.
    """
    for text in texts:
        if not isinstance(text, MaskedText):
            raise TypeError(
                f"embed() requires MaskedText, got {type(text).__name__}. "
                "Route the text through mask_identifiers() first - see PRODUCT.md "
                "architectural rule 2."
            )
        if contains_identifier(text.value):
            raise ValueError(
                "Text reaching the embedder still contains an unmasked identifier. "
                "A MaskedText was constructed without going through mask_identifiers()."
            )
    return [t.value for t in texts]


class GeminiEmbedder:
    def __init__(self, api_key: str, model: str, dims: int) -> None:
        self._api_key = api_key
        self._model = model
        self._dims = dims
        self._client = None

    async def embed(self, texts: list[MaskedText]) -> list[list[float]]:
        from google import genai
        from google.genai import types

        payload = require_masked(texts)

        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)

        response = await self._client.aio.models.embed_content(
            model=self._model,
            contents=payload,
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

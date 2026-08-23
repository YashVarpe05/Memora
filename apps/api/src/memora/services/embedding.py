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


# Gemini rejects a batch of more than 100 with a 400. One calendar export is 353
# events, so this is reached by the first realistic document rather than at scale.
#
# Set to 32 rather than the provider's 100: a 100-item response is roughly 1.5 MB of
# JSON, and those responses were being aborted mid-transfer on a real connection.
# Smaller batches cost more round trips and finish, which is the better trade.
MAX_BATCH = 32

# The free tier also caps embed requests per minute. A 353-event calendar exceeds it
# during a single upload, so a 429 is expected traffic here rather than an error - the
# server tells us how long to wait and we wait.
#
# This is the strongest argument yet for moving ingestion onto the job queue: an HTTP
# upload that sleeps for minutes is not a working upload. See ROADMAP.md, where arq was
# descoped along with audio.
MAX_RETRIES = 6
DEFAULT_BACKOFF_SECONDS = 25.0


def _is_transient(error: Exception) -> bool:
    """Rate limiting and dropped connections are traffic, not bugs.

    Both were hit ingesting the real corpus: a 429 from the free tier's per-minute cap,
    and an aborted response part-way through a large batch.
    """
    text = str(error)
    return (
        "RESOURCE_EXHAUSTED" in text
        or "429" in text
        or "503" in text
        or "payload is not completed" in text
        or "ConnectionAborted" in text
        or "ServerDisconnected" in text
        or isinstance(error, (ConnectionError, TimeoutError))
    )


def _retry_delay(error: Exception) -> float:
    """Seconds the server asked us to wait, or a sane default."""
    import re

    found = re.search(r"retry in ([0-9.]+)s", str(error))
    if found:
        return min(float(found.group(1)) + 1.0, 60.0)
    # A dropped connection has no advice attached; back off briefly and retry.
    if "payload is not completed" in str(error) or "ConnectionAborted" in str(error):
        return 2.0
    return DEFAULT_BACKOFF_SECONDS


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

        vectors: list[list[float]] = []
        for start in range(0, len(payload), MAX_BATCH):
            batch = payload[start : start + MAX_BATCH]
            response = await self._embed_batch(batch, types)
            # Truncated dimensions come back un-normalized; cosine needs unit length.
            vectors.extend(_unit(list(e.values)) for e in response.embeddings)
        return vectors

    async def _embed_batch(self, batch: list[str], types):
        import asyncio

        for attempt in range(MAX_RETRIES):
            try:
                return await self._client.aio.models.embed_content(
                    model=self._model,
                    contents=batch,
                    # This model defaults to 3072. The column is vector(768), so the
                    # size is requested rather than assumed - a mismatch here is an
                    # insert failure.
                    config=types.EmbedContentConfig(output_dimensionality=self._dims),
                )
            except Exception as exc:  # noqa: BLE001 - retried selectively, see below
                if not _is_transient(exc):
                    # Retrying a 400 just makes the same mistake six times.
                    raise
                if attempt == MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(_retry_delay(exc))
        raise RuntimeError("unreachable")


def build_embedder() -> Embedder:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set. Embedding is unavailable.")
    return GeminiEmbedder(
        api_key=settings.gemini_api_key,
        model=settings.embedding_model,
        dims=settings.embedding_dims,
    )

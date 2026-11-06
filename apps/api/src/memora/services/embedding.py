"""Embeddings behind a protocol, so tests never touch the network.

Every implementation takes ``MaskedText`` rather than ``str``. That is the enforcement
point for PRODUCT.md architectural rule 2: there is no ordering of calls that sends raw
extracted text to a hosted API, because the only way to obtain a MaskedText is to call
mask_identifiers().
"""

from __future__ import annotations

import asyncio
import math
import re
import threading
from functools import lru_cache
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
        self.fingerprint = f"gemini:{model}:{dims}:unit:v1"

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
    if settings.embedding_provider == "local":
        return _local_embedder(
            settings.local_embedding_model, settings.local_embedding_revision,
            settings.embedding_dims, settings.local_embedding_threads,
        )
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set. Embedding is unavailable.")
    return GeminiEmbedder(
        api_key=settings.gemini_api_key,
        model=settings.embedding_model,
        dims=settings.embedding_dims,
    )


def embedding_fingerprint(embedder: Embedder | None) -> str | None:
    """Builtin providers are versioned; legacy test/custom doubles remain unlabelled."""
    return getattr(embedder, "fingerprint", None)


async def embed_query(embedder: Embedder, text: MaskedText) -> list[float]:
    """Asymmetric models use a query prefix; legacy providers retain their behavior."""
    method = getattr(embedder, "embed_query", None)
    if method is not None:
        return await method(text)
    return (await embedder.embed([text]))[0]


class LocalE5Embedder:
    """Pinned multilingual E5 on CPU, with separate query/passage prefixes.

    Runtime uses only cached model files. Explicit --warmup downloads the pinned
    snapshot, avoiding network work and surprise downloads during a user's search.
    """

    def __init__(
        self, model: str, revision: str, dims: int = 768, threads: int = 2,
        *, allow_download: bool = False,
    ) -> None:
        if model != "intfloat/multilingual-e5-base" or dims != 768:
            raise ValueError("Local search requires multilingual-e5-base with 768 dimensions.")
        if not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise ValueError("Pin LOCAL_EMBEDDING_REVISION to a full immutable commit SHA.")
        if threads < 1:
            raise ValueError("LOCAL_EMBEDDING_THREADS must be positive.")
        self.model = model
        self.revision = revision
        self.dims = dims
        self.threads = threads
        self.allow_download = allow_download
        self.fingerprint = f"local:{model}@{revision}:768:mean:query-passage:unit:v1"
        self._model = None
        self._lock = threading.Lock()
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    def _encode(self, payload: list[str], prefix: str) -> list[list[float]]:
        if not payload:
            return []
        with self._lock:
            if self._model is None:
                try:
                    import torch
                    from sentence_transformers import SentenceTransformer
                except ImportError as exc:
                    raise RuntimeError(
                        "Install local search with uv sync --group semantic."
                    ) from exc
                torch.set_num_threads(self.threads)
                self._model = SentenceTransformer(
                    self.model, revision=self.revision, device="cpu", trust_remote_code=False,
                    local_files_only=not self.allow_download,
                )
                self._model.max_seq_length = 512
                if self._model.get_sentence_embedding_dimension() != self.dims:
                    self._model = None
                    raise RuntimeError("The local model dimensions do not match the database.")
            vectors = self._model.encode(
                [prefix + text for text in payload], batch_size=8,
                normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False,
                prompt="",
            ).tolist()
        if any(len(vector) != self.dims or not all(math.isfinite(v) for v in vector)
               for vector in vectors):
            raise RuntimeError("The local model returned an invalid embedding.")
        self._ready = True
        return [_unit(vector) for vector in vectors]

    async def embed(self, texts: list[MaskedText]) -> list[list[float]]:
        payload = require_masked(texts)
        return await asyncio.to_thread(self._encode, payload, "passage: ")

    async def embed_query(self, text: MaskedText) -> list[float]:
        payload = require_masked([text])
        return (await asyncio.to_thread(self._encode, payload, "query: "))[0]


@lru_cache(maxsize=1)
def _local_embedder(model: str, revision: str, dims: int, threads: int) -> LocalE5Embedder:
    return LocalE5Embedder(model, revision, dims, threads)


def _warmup() -> None:
    import argparse
    import json

    from memora.services.masking import mask_all, mask_identifiers

    parser = argparse.ArgumentParser(
        description="Download and verify the pinned local search model."
    )
    parser.add_argument("--warmup", action="store_true", required=True)
    parser.parse_args()
    settings = get_settings()
    model = LocalE5Embedder(
        settings.local_embedding_model, settings.local_embedding_revision,
        settings.embedding_dims, settings.local_embedding_threads, allow_download=True,
    )

    async def check():
        documents = [
            "The medical center provides consultations with physicians.",
            "The railway station sells tickets for overnight trains.",
            "The bakery sells freshly baked bread and cakes.",
        ]
        vectors = await model.embed(mask_all(documents))
        query = await model.embed_query(mask_identifiers("Where can I see a doctor?"))
        scores = [sum(a * b for a, b in zip(query, v, strict=True)) for v in vectors]
        best = max(range(len(scores)), key=scores.__getitem__)
        if best != 0:
            raise RuntimeError("Local semantic smoke test did not retrieve the medical document.")
        print(json.dumps({"model": model.fingerprint, "dimensions": len(query),
                          "semantic_smoke_rank": best + 1, "cosine_scores": scores}))

    asyncio.run(check())


if __name__ == "__main__":
    _warmup()

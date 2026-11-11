"""Cross-encoder reranking of the top results: better order, never a refusal.

A bi-encoder scores the query and each passage separately; a cross-encoder reads them
together, so it can tell that a train e-ticket answers "train ticket" while a fee receipt
does not. Measured on a real 1,012-document library (prompts/reranker.md): the first
labelled hit moved to rank 1 for 12 of 22 queries instead of 6, with 20 candidates and the
first 900 characters of each chunk, at about 0.9 s per query on CPU.

It is NOT used to refuse. Its top score overlaps between answerable and absent queries just
as the embedder's does (absent -5.3..-1.0, answerable -4.8..+3.8), so a threshold would hide
real documents.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from memora.services.search import DocumentResult

PASSAGE_CHARS = 900
# Pinned in the model directory name; weights are downloaded and checksummed out of band,
# and never fetched at query time.
MODEL_REVISION = "1427fd652930e4ba29e8149678df786c240d8825"


class Reranker(Protocol):
    def score(self, query: str, passages: list[str]) -> list[float]: ...


def passage_for(contextual_prefix: str, text: str) -> str:
    """What the reranker reads for a chunk: its context line and the start of its text."""
    return f"{contextual_prefix} {text}".strip()[:PASSAGE_CHARS]


class LocalCrossEncoder:
    def __init__(self, model_path: str, threads: int = 2) -> None:
        self.path = Path(model_path).expanduser()
        self.threads = threads
        self._model = None
        self._lock = threading.Lock()

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        with self._lock:
            if self._model is None:
                try:
                    import torch
                    from sentence_transformers import CrossEncoder
                except ImportError as exc:
                    raise RuntimeError(
                        "Install local reranking with uv sync --group semantic."
                    ) from exc
                if not (self.path / "model.safetensors").exists():
                    raise RuntimeError(f"Reranker weights are not at {self.path}.")
                torch.set_num_threads(self.threads)
                self._model = CrossEncoder(str(self.path), device="cpu", max_length=256)
            return [float(v) for v in self._model.predict([(query, p) for p in passages])]


async def rerank_results(
    reranker: Reranker, query: str, ranked: list[DocumentResult], top_n: int
) -> list[DocumentResult]:
    """Reorder the first `top_n` results by the reranker; the rest keep their order after."""
    head, tail = ranked[:top_n], ranked[top_n:]
    if len(head) < 2:
        return ranked
    scores = await asyncio.to_thread(reranker.score, query, [r.passage or r.snippet for r in head])
    order = sorted(range(len(head)), key=lambda i: -scores[i])  # stable: ties keep order
    reordered = [head[i] for i in order] + tail
    return [replace(r, rank=index) for index, r in enumerate(reordered, start=1)]

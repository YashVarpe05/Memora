"""Deterministic doubles. No network, no model downloads, no randomness."""

from __future__ import annotations

import hashlib
import math

from memora.repositories.chunk import ScoredChunk
from memora.services.masking import MaskedText

DIMS = 768


class FakeEmbedder:
    """Same text -> same vector, so cosine similarity is controllable in a test.

    Identical text scores ~1.0; unrelated text scores near 0. That is what makes the
    refusal path testable without tuning anything.
    """

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[MaskedText]) -> list[list[float]]:
        # Same guard as the real embedder. A double that accepted str would let an
        # unmasked path pass its tests and fail in production.
        for text in texts:
            if not isinstance(text, MaskedText):
                raise TypeError(f"embed() requires MaskedText, got {type(text).__name__}")
        self.calls.append([t.value for t in texts])
        return [self._vector(t.value) for t in texts]

    @staticmethod
    def _vector(text: str) -> list[float]:
        """Bag of words hashed into fixed dimensions.

        Text that shares words scores high; unrelated text scores near zero. A pure
        hash of the whole string would be deterministic but would make every pair of
        distinct strings equally distant, which cannot exercise retrieval at all.
        """
        vector = [0.0] * DIMS
        for word in text.lower().split():
            cleaned = "".join(ch for ch in word if ch.isalnum())
            if not cleaned:
                continue
            index = int(hashlib.sha256(cleaned.encode()).hexdigest(), 16) % DIMS
            vector[index] += 1.0
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0.0:
            return [1.0] + [0.0] * (DIMS - 1)
        return [v / norm for v in vector]


class FakeCounter:
    """One token per whitespace-separated word. Deterministic and offline."""

    def count(self, text: str) -> int:
        return len(text.split())

    def split(self, text: str) -> list[str]:
        return text.split()


class FakeGenerator:
    def __init__(self, reply: str = "A grounded answer.") -> None:
        self.reply = reply
        self.calls: list[tuple[str, list[ScoredChunk]]] = []

    async def generate(self, question: str, sources: list[ScoredChunk]) -> str:
        self.calls.append((question, sources))
        return self.reply


def make_pdf(pages: list[str], title: str = "Test Document") -> bytes:
    """A real PDF, built in memory, so extraction is exercised for real."""
    import pymupdf

    doc = pymupdf.open()
    doc.set_metadata({"title": title})
    for body in pages:
        page = doc.new_page()
        page.insert_text((72, 72), body, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data

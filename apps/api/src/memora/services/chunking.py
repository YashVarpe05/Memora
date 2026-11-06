"""Structure-aware chunking.

CLAUDE.md: 300-500 tokens, 10-15% overlap, contextual prefix before embedding.

Token counts come from tiktoken, not a characters-per-token estimate. Chunk
boundaries are an independent variable in every retrieval experiment that follows,
and an approximation means a phase 3 result cannot be attributed to chunking versus
retrieval.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

TARGET_TOKENS = 400
MIN_TOKENS = 300
MAX_TOKENS = 500
OVERLAP_RATIO = 0.12


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...

    def split(self, text: str) -> list[str]: ...


class TiktokenCounter:
    """cl100k_base. Downloads its BPE table once, then works offline from cache."""

    def __init__(self, encoding: str = "cl100k_base") -> None:
        self._name = encoding

    @property
    @lru_cache(maxsize=1)  # noqa: B019 - one encoder per process is the intent
    def _enc(self):
        import tiktoken

        return tiktoken.get_encoding(self._name)

    def count(self, text: str) -> int:
        return len(self._enc.encode(text))

    def split(self, text: str) -> list[str]:
        return [str(t) for t in self._enc.encode(text)]


@dataclass(frozen=True)
class Block:
    """A structural unit from the extractor - a paragraph, or a heading."""

    text: str
    heading: str | None = None
    # 1-based source page for PDFs, None for images and plain text.
    page: int | None = None
    # When the content is about. Set by the calendar and chat parsers.
    occurred_at: object | None = None
    meta: dict | None = None


@dataclass(frozen=True)
class TextChunk:
    text: str
    contextual_prefix: str
    token_count: int
    ordinal: int
    # The page the chunk starts on, so click-through opens on the match.
    page: int | None = None
    occurred_at: object | None = None
    meta: dict | None = None


def _overlap_tail(text: str, counter: TokenCounter, tokens: int) -> str:
    """Roughly the last `tokens` worth of words, for the overlap window."""
    words = text.split()
    kept: list[str] = []
    for word in reversed(words):
        kept.insert(0, word)
        if counter.count(" ".join(kept)) >= tokens:
            break
    return " ".join(kept)


def chunk_blocks(
    blocks: list[Block],
    *,
    title: str,
    counter: TokenCounter,
) -> list[TextChunk]:
    """Pack blocks into 300-500 token chunks without splitting a block when avoidable."""
    chunks: list[TextChunk] = []
    buffer: list[str] = []
    heading: str | None = None
    page: int | None = None
    occurred_at: object | None = None
    meta: dict | None = None
    fresh = False
    overlap_tokens = int(TARGET_TOKENS * OVERLAP_RATIO)

    def flush(carry: bool) -> None:
        nonlocal buffer, fresh
        body = " ".join(buffer).strip()
        if body and fresh:
            chunks.append(
                TextChunk(
                    text=body,
                    contextual_prefix=(title if not heading else f"{title} - {heading}")[:512],
                    token_count=counter.count(body),
                    ordinal=len(chunks),
                    page=page,
                    occurred_at=occurred_at,
                    meta=meta,
                )
            )
        buffer = [_overlap_tail(body, counter, overlap_tokens)] if carry and body else []
        fresh = False

    for block in blocks:
        if block.page != page or (block.heading and heading and block.heading != heading):
            flush(carry=False)
        page = block.page
        if block.heading:
            heading = block.heading
        occurred_at, meta = block.occurred_at, block.meta
        remaining = block.text.strip()
        while remaining:
            # Binary search a bounded text slice; unlike token-ID decoding this never
            # cuts a Unicode code point and also works with the deterministic test counter.
            lo, hi = 1, len(remaining)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if counter.count(remaining[:mid]) <= MAX_TOKENS - overlap_tokens - 8:
                    lo = mid
                else:
                    hi = mid - 1
            end = lo
            if end < len(remaining):
                boundary = remaining.rfind(" ", 0, end)
                if boundary > 0:
                    end = boundary
            piece, remaining = remaining[:end].strip(), remaining[end:].strip()
            if counter.count(" ".join([*buffer, piece])) > MAX_TOKENS:
                flush(carry=True)
            # A very long last word can make a word-based overlap exceed its budget.
            while buffer and counter.count(" ".join([*buffer, piece])) > MAX_TOKENS:
                buffer.pop(0)
            buffer.append(piece)
            fresh = True
            if counter.count(" ".join(buffer)) >= TARGET_TOKENS:
                flush(carry=True)
    flush(carry=False)
    return chunks


def chunk_per_block(blocks: list[Block], *, title: str, counter: TokenCounter) -> list[TextChunk]:
    """One chunk per block, for formats whose structure is the unit of meaning.

    A calendar event and a conversation window are already the right size and the right
    shape. Running a token window over them would cut across unrelated events and embed
    half of one meeting with half of another.
    """
    chunks: list[TextChunk] = []
    for block in blocks:
        body = block.text.strip()
        if not body:
            continue
        prefix = title if block.heading is None else f"{title} - {block.heading}"
        chunks.append(
            TextChunk(
                text=body,
                contextual_prefix=prefix[:512],
                token_count=counter.count(body),
                ordinal=len(chunks),
                page=block.page,
                occurred_at=block.occurred_at,
                meta=block.meta,
            )
        )
    return chunks


def embeddable(chunk: TextChunk) -> str:
    """What actually gets embedded: prefix first, so an isolated chunk keeps its origin."""
    return f"{chunk.contextual_prefix}\n\n{chunk.text}" if chunk.contextual_prefix else chunk.text

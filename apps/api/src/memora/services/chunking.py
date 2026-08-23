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


@dataclass(frozen=True)
class TextChunk:
    text: str
    contextual_prefix: str
    token_count: int
    ordinal: int
    # The page the chunk starts on, so click-through opens on the match.
    page: int | None = None


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
    overlap_tokens = int(TARGET_TOKENS * OVERLAP_RATIO)

    def flush(carry: bool) -> None:
        nonlocal buffer, page
        body = " ".join(buffer).strip()
        if not body:
            return
        prefix = title if heading is None else f"{title} - {heading}"
        chunks.append(
            TextChunk(
                text=body,
                contextual_prefix=prefix[:512],
                token_count=counter.count(body),
                ordinal=len(chunks),
                page=page,
            )
        )
        buffer = [_overlap_tail(body, counter, overlap_tokens)] if carry else []
        # The next chunk starts wherever its first block is.
        page = None

    for block in blocks:
        if block.heading:
            heading = block.heading
        if page is None and block.page is not None:
            # The page a chunk starts on; later blocks may spill onto the next.
            page = block.page
        candidate = " ".join([*buffer, block.text]).strip()
        if counter.count(candidate) > MAX_TOKENS and buffer:
            flush(carry=True)
        buffer.append(block.text)
        if counter.count(" ".join(buffer)) >= TARGET_TOKENS:
            flush(carry=True)

    flush(carry=False)

    # A trailing fragment below MIN_TOKENS is folded back rather than left stranded.
    if len(chunks) > 1 and chunks[-1].token_count < MIN_TOKENS // 2:
        tail = chunks.pop()
        merged = f"{chunks[-1].text} {tail.text}".strip()
        chunks[-1] = TextChunk(
            text=merged,
            contextual_prefix=chunks[-1].contextual_prefix,
            token_count=counter.count(merged),
            ordinal=chunks[-1].ordinal,
            page=chunks[-1].page,
        )
    return chunks


def embeddable(chunk: TextChunk) -> str:
    """What actually gets embedded: prefix first, so an isolated chunk keeps its origin."""
    return f"{chunk.contextual_prefix}\n\n{chunk.text}" if chunk.contextual_prefix else chunk.text

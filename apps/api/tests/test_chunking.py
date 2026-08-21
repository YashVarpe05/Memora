"""Chunking. Token counts come from a deterministic double, not tiktoken."""

from memora.services.chunking import (
    MAX_TOKENS,
    TARGET_TOKENS,
    Block,
    chunk_blocks,
    embeddable,
)

from support import FakeCounter


def blocks(n: int, words: int = 40, heading: str | None = None) -> list[Block]:
    out = []
    for i in range(n):
        out.append(Block(text=" ".join(f"w{i}x{j}" for j in range(words)), heading=heading))
    return out


def test_single_short_block_makes_one_chunk():
    chunks = chunk_blocks(blocks(1, words=20), title="Doc", counter=FakeCounter())
    assert len(chunks) == 1
    assert chunks[0].ordinal == 0


def test_long_input_splits_into_multiple_chunks():
    chunks = chunk_blocks(blocks(30, words=40), title="Doc", counter=FakeCounter())
    assert len(chunks) > 1
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_chunks_respect_the_upper_bound():
    counter = FakeCounter()
    chunks = chunk_blocks(blocks(30, words=40), title="Doc", counter=counter)
    # The overlap carry can push a chunk slightly past the target, but never far.
    assert all(c.token_count <= MAX_TOKENS + TARGET_TOKENS for c in chunks)


def test_consecutive_chunks_overlap():
    chunks = chunk_blocks(blocks(30, words=40), title="Doc", counter=FakeCounter())
    first_tail = set(chunks[0].text.split()[-40:])
    second_head = set(chunks[1].text.split()[:40])
    assert first_tail & second_head, "expected overlap between adjacent chunks"


def test_contextual_prefix_carries_title_and_heading():
    mixed = [Block(text="Intro text here", heading="Section One"), *blocks(2)]
    chunks = chunk_blocks(mixed, title="Doc", counter=FakeCounter())
    assert chunks[0].contextual_prefix == "Doc - Section One"


def test_prefix_is_prepended_before_embedding_only():
    chunk = chunk_blocks(blocks(1, words=10), title="Doc", counter=FakeCounter())[0]
    assert embeddable(chunk).startswith("Doc")
    # The stored text stays clean, so a citation quotes the source and not our prefix.
    assert not chunk.text.startswith("Doc")


def test_empty_input_produces_nothing():
    assert chunk_blocks([], title="Doc", counter=FakeCounter()) == []

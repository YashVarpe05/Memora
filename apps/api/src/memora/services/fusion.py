"""Fusing the text list and the image list.

**The two scores are not comparable and are never compared.** A CLIP text-image
similarity around 0.28 is a strong match; the text pipeline's similarities sit around
0.5-0.8 and it treats 0.5 as weak. A max(), a weighted sum, or a threshold written for
one applied to the other would silently rank every text hit above every image hit
regardless of quality - and this project has already shipped one threshold that measured
the wrong number.

Reciprocal Rank Fusion consumes **ranks**, not scores, so it is indifferent to two
systems having different scales. `RAG.md` already mandates RRF at k=60 for fusing dense
with BM25; this is the same mechanism for the same reason, which is why there is no new
constant to justify.

    score(doc) = sum over lists of  1 / (K + rank_in_that_list)

A document found by both lists outranks one found by either alone. That is the desired
behaviour for an ID card: OCR may catch a few words AND it looks like a card.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

# Same k as the dense+BM25 fusion in RAG.md. Large enough that the difference between
# rank 1 and rank 2 does not dominate agreement between the two lists.
RRF_K = 60


@dataclass(frozen=True)
class FusedDocument:
    memory_id: UUID
    score: float
    text_rank: int | None
    image_rank: int | None

    @property
    def found_by_both(self) -> bool:
        return self.text_rank is not None and self.image_rank is not None


def reciprocal_rank_fusion(
    text_order: list[UUID],
    image_order: list[UUID],
    k: int = RRF_K,
) -> list[FusedDocument]:
    """Fuse two ranked document lists. Order in, order out; no scores cross the boundary.

    Both arguments are lists of memory ids in rank order, which is deliberate: taking
    ranks rather than scored hits makes it impossible for a caller to accidentally hand
    this function two incomparable numbers.
    """
    contributions: dict[UUID, float] = {}
    text_ranks: dict[UUID, int] = {}
    image_ranks: dict[UUID, int] = {}

    for position, memory_id in enumerate(text_order, start=1):
        if memory_id in text_ranks:
            continue  # a document appears once; its best rank is the one that counts
        text_ranks[memory_id] = position
        contributions[memory_id] = contributions.get(memory_id, 0.0) + 1.0 / (k + position)

    for position, memory_id in enumerate(image_order, start=1):
        if memory_id in image_ranks:
            continue
        image_ranks[memory_id] = position
        contributions[memory_id] = contributions.get(memory_id, 0.0) + 1.0 / (k + position)

    fused = [
        FusedDocument(
            memory_id=memory_id,
            score=score,
            text_rank=text_ranks.get(memory_id),
            image_rank=image_ranks.get(memory_id),
        )
        for memory_id, score in contributions.items()
    ]
    # Ties broken by text rank, then image rank, so the order is deterministic. A
    # non-deterministic ranking makes every measurement unreproducible.
    fused.sort(
        key=lambda d: (
            -d.score,
            d.text_rank if d.text_rank is not None else 10**6,
            d.image_rank if d.image_rank is not None else 10**6,
        )
    )
    return fused

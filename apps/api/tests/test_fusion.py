"""Fusing text and image results.

The single property worth protecting: **the two similarity scales never meet.** CLIP
similarities for genuine matches sit near 0.28; text similarities sit near 0.6 and 0.5 is
already weak. Any arithmetic across them ranks every text hit above every image hit
regardless of quality, and it would look like a working system.

RRF consumes ranks, so the scales cannot meet by construction. These tests check that the
construction actually holds.
"""

import uuid

from memora.services.fusion import RRF_K, reciprocal_rank_fusion


def ids(n: int) -> list[uuid.UUID]:
    return [uuid.UUID(int=i) for i in range(1, n + 1)]


def test_a_document_in_both_lists_beats_one_in_either():
    """The ID card case: OCR catches a few words AND it looks like a card."""
    a, b, c = ids(3)

    fused = reciprocal_rank_fusion(text_order=[b, a], image_order=[c, a])

    assert fused[0].memory_id == a, "agreement between the two lists must win"
    assert fused[0].found_by_both


def test_an_image_only_document_can_outrank_a_text_only_one():
    """The group photo. It has no text at all, so it appears in one list only.

    If image hits could never outrank text hits, hero query 7 would still be unanswerable
    and the whole phase would be decorative.
    """
    text_only, image_only = ids(2)

    fused = reciprocal_rank_fusion(text_order=[text_only], image_order=[image_only])

    # Equal ranks in their own lists means equal contribution; neither list is privileged.
    assert {d.memory_id for d in fused} == {text_only, image_only}
    assert fused[0].score == fused[1].score


def test_fusion_takes_ranks_and_cannot_see_scores():
    """Structural, not behavioural.

    The function's signature accepts ranked id lists. There is no parameter through which
    a caller could pass a CLIP similarity and a cosine similarity into the same
    expression, which is what makes the mistake impossible rather than merely avoided.
    """
    import inspect

    params = inspect.signature(reciprocal_rank_fusion).parameters

    assert set(params) == {"text_order", "image_order", "k"}
    for name in ("text_order", "image_order"):
        assert "UUID" in str(params[name].annotation), (
            f"{name} must be ranked ids, not scored hits - a scored hit lets two "
            "incomparable scales into one function"
        )


def test_rank_one_in_both_lists_scores_exactly_twice_the_rrf_term():
    a = ids(1)[0]

    fused = reciprocal_rank_fusion(text_order=[a], image_order=[a])

    assert fused[0].score == 2.0 / (RRF_K + 1)


def test_order_is_deterministic_when_scores_tie():
    """A non-deterministic ranking makes every measurement unreproducible."""
    a, b, c, d = ids(4)

    first = reciprocal_rank_fusion(text_order=[a, b], image_order=[c, d])
    second = reciprocal_rank_fusion(text_order=[a, b], image_order=[c, d])

    assert [x.memory_id for x in first] == [x.memory_id for x in second]


def test_a_repeated_document_counts_once_at_its_best_rank():
    a, b = ids(2)

    fused = reciprocal_rank_fusion(text_order=[a, b, a], image_order=[])

    assert len(fused) == 2
    assert next(d for d in fused if d.memory_id == a).text_rank == 1


def test_empty_image_list_leaves_text_order_intact():
    """Before any image is embedded — the state the corpus is in today."""
    order = ids(4)

    fused = reciprocal_rank_fusion(text_order=order, image_order=[])

    assert [d.memory_id for d in fused] == order
    assert all(d.image_rank is None for d in fused)


def test_both_lists_empty_is_not_an_error():
    assert reciprocal_rank_fusion(text_order=[], image_order=[]) == []

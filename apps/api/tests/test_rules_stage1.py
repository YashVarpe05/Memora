"""Stage 1 without a model.

Measured 2026-09-04: **identical to `qwen2.5:3b` on all 25 gold rows** — same
Recall@1 0.905, same MRR, same outcome row for row. These tests pin the extraction
behaviour that produced that, and the two cases where rules are known to be worse, so a
future change has to break a named assertion rather than a number.
"""

import pytest

from memora.services.rules_query_understanding import RulesQueryUnderstanding


@pytest.fixture
def rules():
    return RulesQueryUnderstanding()


async def test_media_words_become_source_types(rules):
    assert (await rules.extract("that motivation photo")).source_types == ("image",)
    assert (await rules.extract("the whatsapp message")).source_types == ("chat",)
    assert (await rules.extract("my birthday reminders")).source_types == ("calendar",)


async def test_a_thing_that_is_not_a_medium_is_not_a_filter(rules):
    """"document", "file" and "note" name a thing rather than how it arrived, and every
    stored item is a file. A filter that matches everything costs the query its bonus
    without excluding anything."""
    for query in ("the document about drones", "that file i saved", "my notes"):
        assert (await rules.extract(query)).source_types == (), query


async def test_a_sender_is_a_person_not_the_verb(rules):
    """`_SENDER` matches "forwarded" and "shared by" on their own, so the first version
    returned sender="forwarded" for q008 - a filter looking for a person called Forwarded,
    matching nothing and costing the query its bonus. Found by reading the extraction
    before measuring, not by the number being slightly worse."""
    assert (await rules.extract("the whatsapp message from aradhana")).sender == "aradhana"
    assert (await rules.extract("the mail yash sent to rutuja")).sender == "yash"
    assert (await rules.extract("the ai job someone forwarded to me")).sender is None


async def test_a_two_word_name_keeps_only_the_last_word(rules):
    """A known limitation, asserted so it stays known. `_SENDER` captures one word before
    "sent", so "anu priya sent" yields "priya". Substring matching on either side still
    hits the stored sender, which is why q009 passes - degraded, not broken."""
    assert (await rules.extract("the job thing anu priya sent")).sender == "priya"


async def test_relative_dates_resolve_to_a_concrete_range(rules):
    """More than the model does with the same phrase: it defers "last year" for
    resolution, and a table can simply compute it."""
    from datetime import UTC, datetime

    today = datetime(2026, 9, 4, tzinfo=UTC)
    filters = await rules.extract("what i had planned to learn last year", today=today)

    assert filters.after is not None and filters.after.year == 2025
    assert filters.before is not None and filters.before.year == 2025
    assert filters.needs_time_resolution == "last year"


async def test_document_type_comes_from_the_corpus_vocabulary(rules):
    """The same table that types the documents, applied to the query. This is the field
    that moved q024 to rank 1 - and the local model returned None for it on every query,
    because it is not in the schema's required list."""
    assert (await rules.extract("my college ID card")).document_type == "id_card"
    assert (await rules.extract("my passport")).document_type == "passport"


async def test_the_visual_row_gets_no_lexical_route(rules):
    """q025 exists to isolate the visual path. If rules ever extract something here, the
    row has stopped testing what it was written to test."""
    filters = await rules.extract("that rectangular plastic pass with my face printed on it")

    assert filters.document_type is None
    assert filters.source_types == ()
    assert filters.sender is None


async def test_extraction_never_fails(rules):
    """No quota, no transport, no parse. Every failure mode stage1_health.py watches for
    is absent by construction, so a health report of anything else is watching the wrong
    arm."""
    for query in ("", "   ", "!!!", "a" * 4000):
        filters = await rules.extract(query)
        assert filters.failed is False


async def test_the_source_map_cannot_drift_from_the_skip_heuristic():
    """One table. If a word can be mapped to a source type but the skip heuristic does not
    count it as signal, stage 1 is skipped for a query it could have answered."""
    from memora.services.query_signal import SOURCE_WORDS
    from memora.services.rules_query_understanding import SOURCE_MAP

    assert set(SOURCE_MAP) <= SOURCE_WORDS

"""The weak-evidence floor is per embedder: Gemini keeps the legacy constant."""

from memora.config import Settings
from memora.services.retrieval import MIN_SIMILARITY_UNCALIBRATED, has_weak_evidence


def test_default_floor_is_the_legacy_constant() -> None:
    assert has_weak_evidence([0.34]) is True
    assert has_weak_evidence([0.36]) is False
    assert has_weak_evidence([MIN_SIMILARITY_UNCALIBRATED]) is False


def test_a_higher_floor_refuses_scores_the_legacy_floor_accepts() -> None:
    assert has_weak_evidence([0.75], minimum=0.78) is True
    assert has_weak_evidence([0.80], minimum=0.78) is False


def test_nothing_retrieved_is_always_weak() -> None:
    assert has_weak_evidence([], minimum=0.0) is True


def test_local_floor_is_a_setting_and_sits_above_the_legacy_constant() -> None:
    assert Settings(local_min_similarity=0.9).local_min_similarity == 0.9
    assert Settings().local_min_similarity > MIN_SIMILARITY_UNCALIBRATED


def test_local_results_are_uncertain_unless_a_word_or_a_document_type_backs_them():
    from memora.services.retrieval import is_uncertain

    assert is_uncertain(local=True, in_lexical=False, type_match=False, raw_score=0.85) is True
    assert is_uncertain(local=True, in_lexical=True, type_match=False, raw_score=0.7) is False
    assert is_uncertain(local=True, in_lexical=False, type_match=True, raw_score=0.7) is False


def test_gemini_results_keep_the_score_rule():
    from memora.services.retrieval import is_uncertain

    assert is_uncertain(local=False, in_lexical=False, type_match=False, raw_score=0.45) is True
    assert is_uncertain(local=False, in_lexical=False, type_match=False, raw_score=0.6) is False
    assert is_uncertain(local=False, in_lexical=True, type_match=False, raw_score=0.1) is False

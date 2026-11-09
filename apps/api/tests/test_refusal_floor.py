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

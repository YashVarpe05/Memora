"""Dense retrieval and the weak-evidence decision.

Phase 1 is plain cosine similarity. The two-stage pipeline from PRODUCT.md - filters
first, then hybrid search inside them - is phase 3, and its ablation table needs this
number measured before the improvement exists.
"""

from __future__ import annotations

from memora.repositories.chunk import ScoredChunk

# GUESSED, AND NOW MEASURED TO BE WRONG. Do not trust this value.
#
# The name carries the warning on purpose: every read site has to type the word
# UNCALIBRATED, so this cannot quietly harden into a number nobody remembers choosing.
#
# Measured 2026-08-22 against a single 19-page PDF, gemini-embedding-001 at 768 dims:
#
#     genuine hit ("what goes in AGENTS.md")     0.686
#     unrelated but plausible (viva schedule)    0.538
#     pure gibberish                             0.489
#     absent information (bank account)          0.439
#
# Two things follow. Gemini cosine similarity has a high floor - gibberish scores
# 0.489, not ~0 - so 0.35 never fires and the refusal path is currently dead. And the
# usable margin between a real hit and noise is only about 0.15, which is too narrow
# to pick a boundary from four queries against one document.
#
# Raising this to ~0.60 would work for this document and would still be a guess.
# Calibrate when `python -m memora.eval.retrieval` prints PASS: sweep against the gold
# set and take the point where q006-style refusals hold without suppressing real
# answers. Until then, behaviour depending on this value is undecided, not designed.
#
# Read from exactly one place: has_weak_evidence().
MIN_SIMILARITY_UNCALIBRATED = 0.35


def has_weak_evidence(results: list[ScoredChunk]) -> bool:
    """True when nothing retrieved is good enough to answer from.

    PRODUCT.md: when retrieval is weak the system says it doesn't have that. It never
    fills the gap from model knowledge - so this decision is made before the LLM is
    called, not left to the model's judgement.
    """
    if not results:
        return True
    return max(r.similarity for r in results) < MIN_SIMILARITY_UNCALIBRATED

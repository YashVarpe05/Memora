"""Dense retrieval and the weak-evidence decision.

Phase 1 is plain cosine similarity. The two-stage pipeline from PRODUCT.md - filters
first, then hybrid search inside them - is phase 3, and its ablation table needs this
number measured before the improvement exists.
"""

from __future__ import annotations

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

# The SAME decision on CLIP's scale, which is not the text scale and must never be
# compared with it: a CLIP text-image similarity around 0.28 is a strong match, where the
# text pipeline treats 0.5 as weak.
#
# Also uncalibrated, and named so rather than tuned. The one measurement behind it:
# "that photo of me leaning on the balcony at college" scores 0.348 against the correct
# file, while "a group photo of people" tops out at 0.163 against a corpus containing no
# group photo. 0.25 sits between those two observations and nothing more.
MIN_IMAGE_SIMILARITY_UNCALIBRATED = 0.25


def has_weak_evidence(similarities: list[float]) -> bool:
    """True when nothing retrieved is good enough to act on.

    Takes scores rather than chunks so both layers can call it: layer one asks whether
    the top document is worth showing, layer two whether there is enough to answer from.

    PRODUCT.md: when retrieval is weak the system says it doesn't have that. It never
    fills the gap from model knowledge - so this decision is made before the LLM is
    called, not left to the model's judgement.
    """
    if not similarities:
        return True
    return max(similarities) < MIN_SIMILARITY_UNCALIBRATED


def has_weak_image_evidence(similarities: list[float]) -> bool:
    """The same question asked of the visual index, on its own scale.

    Separate function rather than a threshold parameter, so the two numbers cannot be
    passed to each other by accident. A text score judged against 0.25, or a CLIP score
    judged against 0.35, would both look like working code.
    """
    if not similarities:
        return True
    return max(similarities) < MIN_IMAGE_SIMILARITY_UNCALIBRATED

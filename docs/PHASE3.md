# Phase 3 — query understanding

Measured 2026-08-24 against the same indexed corpus as `BASELINE.md` (11 documents,
377 chunks), both arms in one session.

**Provenance note.** These numbers come from a run made while stage 1 was working. The
free-tier `generateContent` quota was exhausted shortly afterwards, and a later run
silently fell back on every query and reported the dense-only numbers under a stage 1
label. That is what prompted the failure-visibility work described below; the harness now
refuses such a run. This file was written by hand from the good run's output and should be
regenerated when quota resets, with `uv run python -m memora.eval.baseline --out
docs/PHASE3.md`.

## Result

| metric | dense only | stage 1 | change |
|---|---|---|---|
| **Recall@1** | 0.842 (16/19) | **0.947 (18/19)** | **+0.105** |
| Recall@5 | 0.947 | 0.947 | — |
| MRR@10 | 0.895 | 0.947 | +0.052 |
| Refusal accuracy | 0.000 (0/2) | 0.000 (0/2) | — |

Two rows moved, both from rank 2 to rank 1. Nothing regressed.

| id | type | dense | stage 1 |
|---|---|---|---|
| q006 | `entity_resolution` | 2 | **1** |
| q007 | `visual_recall` | 2 | **1** |
| q019 | `visual_recall` | miss | miss |
| q020 | `must_refuse` | answered | answered |
| q021 | `must_refuse` | answered | answered |

All other 16 rows were rank 1 in both arms.

## Predictions, marked

Recorded in `prompts/phase-3-query-understanding.md` before implementing.

| prediction | outcome |
|---|---|
| q006 fixed, **but at risk** from strict source-type filtering | **HELD.** Fixed. The risk was real and was avoided by design: stage 1 returned `source_types: ["email", "pdf"]` because the prompt tells it that scanned emails are PDFs. A strict filter on `email` alone would have excluded the answer. |
| q007 fixed — highest confidence | **HELD, but only on the second attempt.** See below. The first implementation made it *worse*, and the cause was not the one predicted. |
| q019 does not move — the control | **HELD.** Still a miss. Its file is not indexed, and nothing in stage 1 could change that. |
| q020 / q021 not fixed by filtering | **HELD.** Both still answered. Refusal is not a filtering problem. |
| Recall@1 will not improve much and may dip | **BROKEN.** It improved by 0.105, the largest single change in the project. Two of nineteen rows is a bigger fraction than the prediction assumed, and nothing regressed. |
| `disambiguation` rows unaffected | **HELD.** All four rank 1 in both arms. |

## The prediction that broke, and what it revealed

q007 was the highest-confidence prediction, and the first implementation **made it
worse** — from rank 2 to outside the top 3.

The filter was correct. Stage 1 returned `source_types: ["image"]` for "the screenshot of
that dashboard with the forms on it", which is exactly right. The damage came from
somewhere else entirely: stage 1 also **rewrote the query** to "dashboard with the forms",
and that rewrite dropped the word carrying the match.

Isolated by embedding each version directly:

| query embedded | target rank | raw similarity |
|---|---|---|
| "the screenshot of that dashboard with the forms on it" | 2 | 0.547 |
| "dashboard with the forms" (stage 1's rewrite) | 4 | 0.509 |

A loss of 0.038 similarity and two ranks — more than the +0.08 source-type boost could
recover, so a *correct* filter still produced a worse result.

**The fix is to trust stage 1 for filters and not for rewriting.** The user's own words
are embedded; `semantic_query` is still returned so it can be inspected, and is no longer
used. With that change q007 goes to rank 1 and the prediction holds.

This is the most useful thing in the run. Query rewriting was never in the plan and was
added without being measured, and it would have been invisible without a prediction to
violate: Recall@1 still rose to 0.895 on the first attempt, so the headline improved while
one row silently regressed.

## Stage 1 cost

An extra model call on every search, before retrieval starts.

- 2.2 s to 3.0 s per query, on the free tier
- Search latency roughly triples: retrieval is tens of milliseconds

That is a real trade-off and belongs in the honest version. Two mitigations exist and
neither is implemented: cache extractions by query text, and skip stage 1 when the query
carries no filterable signal. Both are deferrable — the number is what matters now.

## Refusal is not a threshold problem

Refusal accuracy stayed at 0.000, as predicted. The calibration data explains why no
threshold fixes it:

| score | id | type |
|---|---|---|
| 0.538 | q020 | `must_refuse` |
| 0.554 | q019 | `visual_recall` |
| 0.599 | q017 | `metadata_only` |
| ... | | |
| 0.645 | q004 | `disambiguation` |
| **0.647** | **q021** | **`must_refuse`** |
| 0.651 | q013 | `entity_resolution` |
| ... | | |
| 0.801 | q002 | `content_semantic` |

q020 ("my passport") is the lowest score in the set, so a threshold around 0.55 would
catch it. But **q021 ("my college fee receipt") scores 0.647, above nine genuinely
successful queries.** Catching it would mean refusing q004, q017, q016, q010, q009, q007,
q003 and q013 — eight correct answers thrown away to reject one absent document.

**No single similarity threshold separates absent from present in this corpus.** The
reason is not noise: the calendar genuinely contains events about college and fees, so
there really is something similar. Absence is not detectable as low similarity.

Refusal needs a different signal. Candidates, none tested:

- **Margin between rank 1 and rank 2.** A real match usually stands out; a spurious one
  sits in a flat field of near-identical scores.
- **Document-type agreement.** Stage 1 extracts `document_type: receipt`; if nothing in
  the corpus is a receipt, refuse regardless of similarity. This is the most promising,
  because it tests the same thing the user is asking.
- **Absolute evidence rather than relative.** Does any chunk actually contain the terms.

The scores above are boosted rather than raw — the raw-score capture landed after quota
was exhausted. The interleaving conclusion does not depend on it: q021 outranks nine
correct answers either way.

## Known limitations, unchanged

- `document_identity` remains unmeasured: no ID-card photo in the corpus.
- Three corpus files contain no extractable text and are unfindable by any query.
- Tesseract is the only working OCR engine on this hardware.
- 19 retrieval rows means one row is 0.053 of Recall@1. Read absolute counts, not
  fractions, and do not read significance into a difference of one.

# Refusal calibration for the local E5 embedder

Status: PROPOSED 2026-11-09. Not approved. Nothing here is implemented.

## Problem
With local `multilingual-e5-base`, an unrelated query is not refused. Measured 2026-11-09
on a 3-document synthetic library through `POST /search`:

| query | top result | raw score |
|---|---|---|
| proof of my address (real hit) | electricity bill | 0.812 |
| college payment confirmation (real hit) | tuition receipt | 0.834 |
| holiday stay reservation (real hit) | hotel booking | 0.843 |
| something about a pet dog (no such document) | hotel booking | **0.752** |

`has_weak_evidence()` in `services/retrieval.py` refuses below one global constant,
`MIN_SIMILARITY_UNCALIBRATED = 0.35`, which its own comment calls dead for Gemini
(gibberish scored 0.489). E5 cosine scores sit even higher (about 0.70-0.85), so the same
constant can never fire. The record is already 2 of 4 refusals correct (`docs/PHASE3B.md`),
and the repo's rule is that a threshold needs a measurement behind it.

## Approach
1. **Threshold per embedder, not one constant.** Key a small table by
   `embedding_fingerprint()`; an embedder with no entry keeps today's behaviour, so Gemini
   results and the committed baselines do not change. The scales must never be compared
   (the CLIP threshold already follows this rule).
2. **Do not trust the score alone.** A real hit in this model is only ~0.06-0.09 above
   noise, too narrow for one cutoff. Refuse only when BOTH hold: raw top score is below the
   embedder's threshold, AND there is no corroborating evidence - no query content word in
   the lexical index (`services/lexical.py`) and no stage 1 filter match (document type,
   sender, date). "Aadhaar card" style queries therefore survive a low score because the
   document-type label corroborates.
3. **Calibrate on held-out data.** Sweep the threshold on a calibration split and report on
   a separate test split. Take the smallest threshold that keeps Recall@1 and Recall@5 at
   their current values, then report refusal accuracy at that point. Do not pick the value
   that maximises refusal alone; a wrong refusal hides a real document, which is the worse
   error for this product.
4. **Commit the before-number first** (CLAUDE.md: the ablation needs a baseline taken before
   the change): run `python -m memora.eval.retrieval` with `EMBEDDING_PROVIDER=local` on the
   unchanged code and record it in `docs/`.

## Mechanism check on synthetic data (2026-11-09, dense scores only, no server)
Claude drafted 34 queries (`context/my-queries.txt`; lazy, vague, normal, Hindi/Marathi) and
a 16-document synthetic pack, then embedded both with the real local model. This tests the
mechanism, not accuracy on real documents.
- Dense Recall@1 24/25, Recall@3 25/25 (the one miss is the single word "marksheet").
- Top score, 25 queries with an answer: min 0.752, median 0.825, max 0.901.
- Top score, 9 queries with no answer: min 0.760, median 0.803, max 0.821.
- The ranges overlap. The largest cutoff that loses no real query is 0.750, which refuses
  0 of 9 absent queries. **A score threshold alone cannot work with this model.**
- A word-match check (query content words against document text) alone refuses 6 of 9 absent
  queries but also drops "pan" and "cv", and three absent queries still match a generic word
  ("registration", "tax", "receipt"). Hence both signals plus document-type labels, and
  weighting rare words above common ones, rather than any single rule.

## Data this needs (blocked on the owner)
- The personal gold corpus is not on this machine (`data/corpus` is empty), so the gold
  eval cannot run. Calibration needs the owner's 20 real queries (`context/my-queries.txt`,
  no ID numbers) plus about 10 queries for documents they know they do not have. Synthetic
  data can test the mechanism, not choose the number.

## Acceptance
- Unit tests: per-embedder lookup; no entry -> legacy behaviour; low score + lexical hit
  -> answered; low score + no corroboration -> refused; Gemini path unchanged.
- On the owner's data: Recall@1 and Recall@5 not below the recorded local-E5 baseline;
  must-refuse accuracy reported with the split it was measured on.
- Gates: `uv run pytest && uv run ruff check .`, `python -m memora.eval.retrieval`, with
  `docker compose ps` checked first (a run with containers down is not evidence).

## Not in scope
New eval tooling, changing Gemini thresholds, a reranker, an LLM-based relevance judge,
the CLIP image threshold.

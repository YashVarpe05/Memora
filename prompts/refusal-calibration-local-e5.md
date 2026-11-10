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

## Implemented 2026-11-10 (synthetic data; floor NOT calibrated on real documents)
`has_weak_evidence(similarities, minimum)` takes a floor; the search router uses the new
`local_min_similarity` setting when `EMBEDDING_PROVIDER=local` and the legacy 0.35 otherwise.
A recognised document type present in the ranked results now corroborates a low score, as
a lexical match already did. Through the real pipeline (16 synthetic documents indexed with
the real model, 25 answerable + 9 absent queries):

| floor | absent refused | answerable falsely refused | Recall@1 |
|---|---|---|---|
| 0.35 (before) | 1/9 | 0/25 | 24/25 |
| **0.78 (default)** | **3/9** | **0/25** | **24/25** |
| 0.80-0.86 | 4-5/9 | 1/25 ("cv") | 23/25 |

0.78 is the highest floor that hides no answerable query. Six absent queries are still
answered: their words ("registration", "tax", "receipt", "certificate") match generic terms
in the library. Weighting rare words above common ones is the next change and needs the
owner's real queries to tune; it is not built.

## Rare-word weighting: measured, rejected (2026-11-10)
Tried summing each matched query word's IDF over the 16-document pack and refusing below a
cutoff. No cutoff separates the groups: absent "GST registration certificate" and "property
tax receipt" both score 4.34, the same as answerable "light bill" and "fee receipt";
absent "vehicle registration RC book" (2.43) ties several answerable one-word queries. A
word that is rare is still the wrong document ("tax" appears in the PAN card). Not built.
What would help is judging the whole query against the document (a cross-encoder or an
LLM relevance check), which is out of scope for now. The honest limit today: with the
local model, some absent queries whose words appear elsewhere in the library are answered.

## Real phone library, 1,012 documents (2026-11-11): score cutoffs do not work
A temporary token (removed afterwards) let the evaluation read the phone's library through the
API; only types, scores and ranks were printed. 146 documents carry a document type, 866 do not.
- Type-labelled queries: first labelled hit at rank 1 for 15 of 22 queries, within the top 5
  for 19 of 22. Misses are semantic-only phrasings ("my school results", "payment
  confirmation", "id card") and "train ticket" (two unlabelled results above the first Ticket).
- Absent topics (pet dog, biryani, football, weather, guitar, moon landing, a visa): 0 of 7
  refused. Their top raw scores were 0.816-0.845; answerable semantic-only queries scored
  0.822-0.857. The top score, the gap between rank 1 and rank 10 or 30, and the spread of the
  top 30 all overlap completely (e.g. absent "biryani recipe" gap 0.046, answerable
  "aadhaar" gap 0.048). **No score-based "nothing found" rule is viable with this model.**
- Done instead: for the local model a result is flagged "Possible match" unless a query word
  or a recognised document type backs it, and the search page says "No confident match" when
  every result is flagged. Honest instead of refusing; a refusal rule would hide real hits.
- What would work, not built: a cross-encoder reranker or a small local LLM judging whether
  the top snippets answer the query, both extra model downloads and CPU time per query.

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

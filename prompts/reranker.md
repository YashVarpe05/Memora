# Cross-encoder reranker: better ranking and a real "nothing found"

Status: MEASURED and INTEGRATED for ranking only, default OFF (2026-11-11). Not used to refuse.
**Recommendation: leave it off.** On the full search pipeline it gains one query per language group
for about +1 s per search (see the correction below).

## Problem (measured, not assumed)
On the owner's real 1,012-document library with the local E5 embedder (see
`refusal-calibration-local-e5.md`):
- No score, score gap or score spread separates answerable queries from absent ones. 0 of 7
  absent topics were refused; their top raw scores (0.816-0.845) overlap answerable
  semantic-only queries (0.822-0.857).
- Semantic phrasings miss ("my school results", "payment confirmation", "id card").
- Bi-encoder similarity cannot say "this passage ANSWERS the query"; a cross-encoder reads the
  query and the passage together and can.

## Model
`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` at revision
`1427fd652930e4ba29e8149678df786c240d8825` (multilingual mMARCO, includes Hindi; XLM-R
vocabulary covers Marathi). About 118M parameters, ~470 MB, CPU. Pinned by SHA like E5.

## Measurement (before any integration)
Use the same queries as the earlier real-library run: 22 type-labelled queries and 7 clean
absent topics, through the API with a temporary token that is removed afterwards; print types,
scores and ranks only. For each query take the top 30 documents' best snippets, score
(query, snippet) with the cross-encoder, and report:
1. Does the reranked order improve first-labelled-hit rank (15/22 at rank 1 today)?
2. Does the top reranker score separate answerable from absent queries? Report the ranges and
   the best threshold with its false-refusal count. Integrate refusal only if the separation
   is clean, not merely better.
3. CPU time per query for 30 candidates.

## Integration (only if 1-3 justify it)
Behind a setting (`RERANKER=off|local`, default off), applied after RRF and before refusal;
refusal threshold calibrated from this measurement and stored with the model fingerprint, as
the embedder floor is. Tests with a fake reranker; no network at query time (cached weights).

## Not in scope
An LLM judge, training or fine-tuning, a larger reranker, or reranking images.

## Gates
`uv run pytest && uv run ruff check .`; the measurement numbers recorded here.

## Results (2026-11-11, real phone library, 1,012 documents)
Measured in-process as the owner's library (an alternative to a temporary API token, which
would have replaced the phone's own login); only types, scores and ranks were printed. Oracle:
the rule-based document type, which exists for 146 of 1,012 documents, so the numbers are
relative, not absolute. 22 type-labelled queries, dense candidates (top 60 chunks, best chunk
per document).

| order | first labelled hit at rank 1 | within top 5 | time per query |
|---|---|---|---|
| dense only | 6 / 22 | 12 / 22 | - |
| reranked, top 30, 900 chars | 12 / 22 | 13 / 22 | 1.5 s |
| reranked, top 20, 900 chars | **12 / 22** | **14 / 22** | **0.86 s** |
| reranked, top 15, 900 chars | 10 / 22 | 13 / 22 | 0.65 s |
| reranked, top 30, 300 chars | 7 / 22 | 13 / 22 | 0.72 s |
| fused with the dense order (RRF), top 20 | 11 / 22 | 13 / 22 | 0.87 s |

- Passage length matters most: 900 characters gave 12/22 at rank 1 against 7/22 for 300, so
  results carry the start of the matched chunk (`passage`, never sent to clients), not the
  280-character snippet. Pure reranker order beat rank fusion.
- "Nothing found": NOT solved. Top reranker score, answerable queries: -4.78 to +3.84, median
  -3.00; absent topics (7): -5.27 to -1.04, median -3.57. A threshold of -2.0 refuses 6 of 7
  absent queries but wrongly refuses 16 of 22 answerable ones. The reranker is used for order only.
- Hindi: a first spot check ("मेरा आधार" against a Hindi Aadhaar text) separated poorly (-6.4 vs
  -6.6), so Hindi and Marathi queries are the weak area for this model.
- Six of the 22 queries have no labelled document among the dense top candidates; those are
  candidate-recall misses that reranking cannot fix (hybrid search covers some of them).

## Integration
`RERANKER=off|local` (default off), `reranker_top_n` 20. `GET /search` reorders the first 20
results by the cross-encoder before the refusal decision, which does not read it. Weights are
cached and checksummed (sha256 5daeca24...), never fetched at query time, at
`~/.cache/memora-models/mmarco-mMiniLMv2-L12-H384-v1-1427fd65`. End to end with the real
model on a small library: "train ticket" put the ticket documents first; first request 2.1 s
(model load), later requests about 1 s on 4 CPU threads. Tests use a fake reranker.

## Correction: the full pipeline, Hindi and Marathi (2026-11-11)
The table above compared the reranker with DENSE order only. The product's real order already
adds lexical matches and document-type boosts, which close most of that gap. Re-measured through
the real `/search` pipeline (in-process, the owner's library, types and ranks only), reranker
off vs on, first labelled hit:

| queries | reranker | rank 1 | within top 5 | median time |
|---|---|---|---|---|
| English (20) | off | 14 | 18 | 0.64 s |
| English (20) | on | 15 | 18 | 1.61 s |
| Hindi, Marathi, Hinglish (23) | off | 13 | 16 | 0.62 s |
| Hindi, Marathi, Hinglish (23) | on | 14 | 15 | 1.65 s |

- The reranker fixes one query per group ("train ticket", one Hindi query), and it lowers
  two Hindi queries from rank 4-6 to rank 10 ("रेल का टिकट"-type phrasings), losing one top-5
  hit. A net gain of about one query in 20, for roughly 1 s more per search.
- Dense-only (no hybrid) Hindi/Marathi queries are weak by themselves: rank 1 for 4 of 23
  dense, 7 of 23 reranked. The hybrid pipeline reaches 13 of 23 without the reranker, mostly
  because its document-type and word matching handles Devanagari type words.
- 7 of the 23 Hindi/Marathi queries find no labelled document in the top 10 even with the
  reranker; those are retrieval misses, not ordering.
- Lesson recorded: always measure a re-ranking component on top of the pipeline that ships, not
  on its first stage.

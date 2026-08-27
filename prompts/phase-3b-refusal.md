# Phase 3b — refusal via document-type agreement

**Status: approved. Blocked on a measurement, not on approval — see sequencing.**

## REVISED 2026-08-27 — the constraint this plan was written under is gone

**Stage 1 now runs locally by default** (`qwen2.5:3b` via Ollama, measured at Recall@1
0.895 — see `PHASE3-LOCAL.md`). Every budget argument below was written when stage 1 was a
metered hosted call, and none of it still applies:

| the plan said | now |
|---|---|
| "this plan spends zero additional calls" — the design was shaped to avoid a second call | **irrelevant.** Local calls are unmetered. A second call costs latency, not budget. |
| "this phase costs one cold cache warm — 21 calls against a 20/day ceiling, spanning two days" | **zero.** No cache, no ceiling, no waiting. |
| "PHASE3C and phase 3b cannot share a day — 13 + 13 against a ceiling of 20" | **no such constraint.** Both can run in one afternoon. |
| "any refusal design has to state its call cost before it is built" | still good practice, but the cost is now latency only |

**This is a second, unplanned benefit of going local, and it is worth stating in the
report.** Local stage 1 was argued for on privacy (`PRODUCT.md`) and then on
reproducibility (`MODEL-RISK.md`). The third benefit only became visible after the switch:
**the prompt is now free to iterate on.**

Every prompt change until now invalidated the entire stage 1 cache — the key is
model + prompt + query — and cost a two-day cold re-measurement against a 20/day ceiling.
That is why the screenshot sentence in phase 3d sat *applied but unmeasured* for a day, and
why this refusal design was contorted to avoid a second call it could not afford. **A
metered extractor does not just limit throughput; it freezes the prompt.** An unmetered one
makes prompt engineering an experiment you can run rather than a change you must justify.

The design below is otherwise unchanged, because it was sound for reasons independent of
cost: document-type agreement tests what the user asked for, rather than a proxy for it.

## Goal## Goal

Refusal accuracy off 0.000, without discarding correct answers, and **without a second
generate call per query**.

## What I read

- `docs/PHASE3.md` — the score distribution, the budget, the wrong-filter result
- `docs/BASELINE.md` — refusal 0.000 in both arms
- `apps/api/src/memora/services/retrieval.py` — `MIN_SIMILARITY_UNCALIBRATED`, still 0.35
- `apps/api/src/memora/services/query_understanding.py` — stage 1 already returns
  `source_types` and could return `document_type` at no extra cost
- `data/eval-runs/stage1-cache.json` — 18 extractions, 7 with no usable filter

## The budget constraint, stated before the design

**20 generate calls per day, per model. Stage 1 already spends one per search.**

A refusal design needing a second call halves the product's throughput to **10 searches a
day**, which is below what a defence demo can safely absorb once rehearsal is counted.

**So this plan spends zero additional calls.** `document_type` is added to stage 1's
existing JSON response — a longer reply from a call already being made. The comparison
against the corpus is a database lookup, not a model call.

If that turns out to need its own call, the plan stops and the trade-off comes back for a
decision rather than being absorbed.

## Why a threshold cannot work — measured, not assumed

```
0.538  q020  must_refuse       ← separable
...
0.647  q021  must_refuse       ← above NINE correct answers
...
0.775  q005  content_semantic
```

Catching q021 with a threshold means refusing q004, q017, q016, q010, q009, q007, q003 and
q013 — eight correct answers for one absent document. The calendar genuinely contains
events about college and fees, so the similarity is real. **Absence is not low
similarity**, and no calibration of `MIN_SIMILARITY_UNCALIBRATED` changes that.

## The design

Stage 1 gains one field:

```
document_type   aadhaar | pan | marksheet | receipt | admit_card | id_card |
                letter | invoice | ticket | null
```

At ingest, each document is labelled with the same vocabulary — from OCR text, filename,
and existing metadata — and stored on `Memory.document_type`.

Refusal becomes: **stage 1 asked for a `receipt`; the corpus contains no document typed
`receipt`; refuse regardless of similarity.** It tests the thing the user asked for rather
than a proxy for it.

Where `document_type` is null — most queries — nothing changes and the existing path runs.

## Predictions, written before implementing

| row | prediction | why |
|---|---|---|
| **q021** "my college fee receipt" | **refused** | Explicitly names a document type. Nothing in the corpus is a receipt, so type disagreement fires and the 0.647 similarity becomes irrelevant. This is the row the design is for. |
| **q020** "my passport" | **refused** | Same mechanism. Also the only row a threshold could have caught, so it should now be caught twice over. |
| **q019** "that photo of me on the balcony" | **must NOT be refused — the control** | It is a genuine query whose file happens to be unindexed. It names no document type, so the new rule must not touch it. It stays a miss, not a refusal. If it flips to refused, the rule is firing on absence-of-match rather than absence-of-type, which is the threshold failure wearing a new name. |
| Recall@1 | **unchanged at 0.947** | The rule only fires when stage 1 names a type and the corpus has none. No answerable row should be affected. |

### Which answerable rows might be wrongly refused

This is the failure mode the design introduces, so it is predicted rather than discovered.

| row | risk | reasoning |
|---|---|---|
| **q017** "where are my birthday reminders kept" | **highest** | "reminders" could be extracted as a document type. The answer is a calendar, which will not be typed `reminder`. Most likely false refusal. |
| **q005** "the list of drone topics i was supposed to learn" | moderate | "list" could be read as a type. The answer is a scanned email typed `letter` or null. |
| **q010** "the tcs job where they asked to send cv on email" | moderate | "cv" is a document type in its own right, and the answer is a screenshot *about* a CV, not a CV. Type would be asked for and not found. |
| **q018** "the youtube course link i saved in my calendar" | low | "link" is not really a document type, but a permissive extractor might emit one. |
| **q001, q007** screenshot queries | low | "screenshot" should map to `source_type`, not `document_type`. If the extractor conflates them, both break. |

**Predicted cost: 1 to 2 false refusals out of 19**, most likely q017. If more than two
answerable rows are refused, the vocabulary is too permissive and the rule should require
type agreement only for a closed list of identity-document types — the ones the product is
actually about — rather than any noun the model volunteers.

## Files that will change

**Create**
```
services/document_type.py    the vocabulary, ingest-time labelling, agreement check
tests/test_document_type.py
tests/test_refusal.py
migrations/versions/0004_document_type.py
```

**Modify**
```
db/models/memory.py                    + document_type
services/query_understanding.py        + document_type in the schema and prompt
services/retrieval.py                  refusal takes type agreement, not just a score
api/routers/search.py                  report the refusal reason
eval/baseline.py                       report false refusals separately from misses
```

## Where the refusal has to be visible

A refusal is a result the user has to be able to read, in the place the search happened.
`api/routers/search.py` reports the reason, and the UI has to render it — the same lesson
the phase-3 guard produced twice over.

**The degraded banner currently lives in the chat view and polls `/health/ready` every
30 s.** That is right for now, because the chat view is the only screen there is. It
belongs on the **search screen** once one exists: the degradation harms search results, so
the warning has to appear where the harm lands, not on an adjacent page the user may never
open. The same applies to a refusal — it is a property of a search, not of the app.

Carry this forward when the search UI is built. Until then the banner is correctly placed
and incorrectly located, which is worth stating rather than forgetting.

## Acceptance criteria

1. q020 and q021 both refused. Refusal accuracy 1.000.
2. q019 **not** refused. Still a miss.
3. Recall@1 stays at 0.947 or the regression is named row by row.
4. False refusals reported separately from retrieval misses — conflating them would hide
   exactly the harm this introduces.
5. Zero additional generate calls per search, asserted by a test that counts calls.
6. A document type stage 1 has never seen does not crash anything; unknown types are
   treated as null.

## Checks to run

```
cd apps/api && uv run pytest && uv run ruff check . && uv run alembic upgrade head
cd apps/api && uv run python -m memora.eval.baseline --local-model qwen2.5:3b-instruct --out docs/PHASE3B.md
```

**Costs nothing and can be re-run as often as needed.** No cache flag: the cache exists to
conserve a metered quota and there is none. Re-running after a prompt tweak is now the
normal way to work rather than a two-day commitment.

## Risks

**The vocabulary is the whole design.** Too narrow and q021 is missed; too broad and
answerable rows get refused. The prediction table above is the test of that, and the
fallback is restricting agreement to identity-document types only.

**Ingest-time labelling is a second classifier**, and a wrong label is as harmful as a
wrong filter — result B in `PHASE3.md`. It should be rule-based first (filename and OCR
keywords), not model-based, so it costs nothing and fails predictably.

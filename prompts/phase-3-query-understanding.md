# Phase 3 — query understanding

**Status: plan only. Nothing implemented pending approval.**

## Goal

Two numbers from `BASELINE.md` move: refusal accuracy off 0.000, and the calendar stops
winning queries it has no business answering.

## What I read

- `docs/BASELINE.md` — Recall@1 0.842, Recall@5 0.947, MRR@10 0.895, refusal 0.000
- `docs/PRODUCT.md` — the stage 1 filter contract and architectural rule 1
- `apps/api/src/memora/services/retrieval.py` — `MIN_SIMILARITY_UNCALIBRATED`, measured
  wrong and still unset
- `apps/api/src/memora/services/search.py` — adaptive window, best-chunk document scoring
- `apps/api/src/memora/db/models/{memory,chunk}.py` — `sender`, `occurred_at`, `meta`,
  `source_type` all exist and are unused by retrieval
- `apps/api/src/memora/eval/baseline.py` — 21 embeds per run now, so sweeping is affordable

## Predictions, made before implementing

Written first on purpose. A prediction made in advance is falsifiable; a result explained
afterwards is not. If these turn out wrong, that is the interesting outcome and it goes in
the report as-is.

| failure | prediction | why |
|---|---|---|
| **q006** "the mail yash sent to rutuja" (rank 2) | **fixed — but at risk** | Two entity names and a strong source signal. Filtering away the calendar leaves `mail.pdf` as the only document naming both. **The risk is the fix:** `mail.pdf` has `source_type = pdf`, not `email`, because it is a scanned print of a Gmail message. A stage 1 that extracts `source_type: email` and filters strictly will *exclude the correct answer* and make this worse than baseline. |
| **q007** "the screenshot of that dashboard with the forms on it" (rank 2) | **fixed** | "screenshot" is an unambiguous `source_type: image` signal, and the calendar cannot survive that filter. Highest-confidence prediction here. |
| **q019** "that photo of me leaning on the balcony at college" (miss) | **not fixed** | The file is not in the index at all — it was rejected at upload for having no extractable text. No query understanding finds a document that was never indexed. **This is the control:** if q019 improves, the measurement is wrong, not the system. |
| **q020 / q021** refusal rows (both answered) | **not fixed by filtering alone** | Filtering changes *which* documents compete, not whether the winner clears a threshold. "my passport" carries no source-type signal, so the pool barely narrows and something still ranks first. Refusal needs calibration, which is a separate change from stage 1. |

Two further predictions worth recording:

- **Recall@1 will not improve much, and may dip.** It is already 16/19; only two rows are
  fixable by filtering, and a strict filter can lose a correct answer (q006). The metric
  that should move is refusal accuracy.
- **The three `disambiguation` rows will be unaffected.** They already pass, and they are
  decided by content similarity between three near-identical synopses. Filtering does not
  help discriminate within one source type — that is a reranking problem, and reranking is
  first on the cut list.

## Assumptions

**1. Filters are soft, not hard.** The q006 risk above is the argument. A hard
`source_type = email` filter is a guess about the corpus made by a model that has not
seen it; when it is wrong the correct answer becomes unreachable and Recall@1 falls. A
soft filter — boost matching documents, demote non-matching, exclude nothing — keeps the
correct answer reachable when stage 1 misjudges. **This is the assumption most worth
arguing with**, and the ablation should test both.

**2. Calibration is a sweep against recorded scores, not another guess.** The baseline
already captured `top_score` per query. Sweeping the threshold across that distribution
and picking the point that maximises refusal accuracy without losing Recall@1 is a
measurement. Picking 0.6 because gibberish scored 0.489 is the same mistake as picking
0.35 was.

**3. The renderer must report the score distribution.** It captures `top_score` and does
not print it, so the calibration data is thrown away on every run. That is a one-line fix
and it has to happen before the sweep, not after.

**4. Stage 1 costs one LLM call per query.** That is layer *two* territory by the letter
of architectural rule 1, which says layer one runs without an LLM. The rule's purpose is
that no document content reaches a third party — and stage 1 sends only the user's own
query, never a document. The rule needs a sentence distinguishing "no document content in
a prompt" from "no model call at all", or the first honest implementation violates it.

## Files that will change

**Create**
```
services/query_understanding.py    natural language -> filters + semantic_query
services/calibration.py            threshold sweep over recorded scores
tests/test_query_understanding.py
tests/test_calibration.py
prompts/                            (this file)
```

**Modify**
```
services/retrieval.py       MIN_SIMILARITY_UNCALIBRATED -> a calibrated constant
services/search.py          accept filters, apply as boosts
repositories/chunk.py       filtered search over source_type, sender, occurred_at
api/routers/search.py       run stage 1, report the extracted filters
eval/baseline.py            report the score distribution; --no-stage1 for the ablation
docs/PRODUCT.md             architectural rule 1: query text vs document content
```

## Implementation requirements

**Stage 1.** One call, returning the `PRODUCT.md` contract: `document_type`, `sender`,
`source_type`, `date_range`, `entities`, `semantic_query`, `needs_time_resolution`. The
prompt gets the corpus's actual source types, because a model guessing `email` for a
scanned PDF is exactly the q006 failure.

**Filters as boosts.** A document matching the extracted `source_type` gets its score
multiplied by a boost; non-matching documents are demoted, not removed. `occurred_at`
handles `date_range`. `sender` matches on `Memory.sender`.

**Calibration.** A sweep over the recorded score distribution, reporting refusal accuracy
and Recall@1 at each candidate threshold, and the chosen value written into the constant
with the sweep table beside it. The constant stops being named `UNCALIBRATED` only when
it has actually been calibrated.

**Ablation.** `--no-stage1` runs the old path, so the table is baseline vs stage 1 on the
same corpus in the same session, not a comparison across two different days.

## Security requirements

- Stage 1 receives the query only. No document text, no snippets, no filenames.
- The query is masked before it reaches the model, exactly as it is before embedding.
- Extracted filters are data. They become bound parameters, never interpolated SQL.
- A malformed or hostile stage 1 response falls back to unfiltered dense search rather
  than failing the request — a search that degrades is better than a search that 500s.

## Acceptance criteria

1. Refusal accuracy > 0.000, achieved by a calibrated threshold rather than a guess.
2. Recall@1 does not regress below the 0.842 baseline.
3. q007 moves to rank 1.
4. q019 does not move. If it does, the measurement is wrong.
5. The ablation table shows baseline and stage 1 measured in the same run.
6. Every prediction above is marked correct or wrong in the results, including the wrong
   ones.
7. Stage 1 never receives document content — asserted on the prompt, not the behaviour.

## Checks to run

```
cd apps/api && uv run pytest && uv run ruff check .
cd apps/api && uv run python -m memora.eval.baseline --out docs/PHASE3.md
```

## How to verify

Run the eval with and without stage 1 in one session and compare the two tables. Then
read the predictions above against the results and mark each one. The value of the
exercise is in the ones that were wrong.

## Risks

**The corpus is small enough that one row moves Recall@1 by 0.053.** With 19 retrieval
rows, a single query changing rank is a five-point swing. Report absolute counts next to
the fractions, and resist reading significance into a difference of one.

**A strict filter can lose more than it gains.** See q006. The soft-filter assumption
exists to bound that, and the ablation should measure it rather than assume it.

# Phase 3 — query understanding

Measured 2026-08-24 against the same indexed corpus as `BASELINE.md` (11 documents,
377 chunks).

**Provenance.** The headline numbers come from a run made while stage 1 was working on
`gemini-2.5-flash`, transcribed by hand from console output because a later run
overwrote the file. Every run is now archived under `data/eval-runs/` so that cannot
recur. Regenerate with `uv run python -m memora.eval.baseline --out docs/PHASE3.md` when
the daily quota allows — see the budget section for why that is not simply "tomorrow".

## Result

| metric | dense only | stage 1 | change |
|---|---|---|---|
| **Recall@1** | 0.842 (16/19) | **0.947 (18/19)** | **+0.105** |
| Recall@5 | 0.947 | 0.947 | — |
| MRR@10 | 0.895 | 0.947 | +0.052 |
| Refusal accuracy | 0.000 (0/2) | 0.000 (0/2) | — |

q006 and q007 moved rank 2 → 1. Nothing regressed. The other 16 answerable rows were
rank 1 in both arms; q019 missed in both; q020 and q021 answered in both.

## Predictions, marked

Recorded in `prompts/phase-3-query-understanding.md` before implementing.

| prediction | outcome |
|---|---|
| q006 fixed, **at risk** from strict source-type filtering | **HELD.** Stage 1 returned `["email", "pdf"]` because the prompt states that scanned emails are PDFs. A strict `email` filter would have excluded the answer. |
| q007 fixed — highest confidence | **HELD, on the second attempt.** The first made it worse, for an unpredicted reason. See below. |
| q019 does not move — the control | **HELD.** Still a miss; its file is not indexed. |
| q020 / q021 not fixed by filtering | **HELD.** Refusal is not a filtering problem. |
| Recall@1 will not improve much, may dip | **BROKEN.** +0.105, the largest single change in the project. |
| `disambiguation` unaffected | **HELD.** |

## The methodology finding

q007 was the highest-confidence prediction, and the first implementation **made it worse**
— rank 2 to outside the top 3 — while **Recall@1 still rose to 0.895**.

The headline improved and a row silently regressed. Without a written prediction naming
q007 specifically, that regression is invisible: the summary metric looked like a win, and
query rewriting would have shipped as an improvement while costing accuracy elsewhere.

The cause was not the filter. Stage 1 correctly returned `source_types: ["image"]` for
"the screenshot of that dashboard with the forms on it". The damage came from stage 1 also
**rewriting the query** to "dashboard with the forms", dropping the word carrying the
match:

| query embedded | rank | raw similarity |
|---|---|---|
| the user's own words | 2 | 0.547 |
| stage 1's rewrite | 4 | 0.509 |

A loss larger than the +0.08 boost could recover, so a *correct* filter still produced a
worse result. **Stage 1 is trusted for filters, not for rewriting.** The user's words are
the query; stage 1's job is constraints, not paraphrase.

This is the argument for pre-registered predictions, demonstrated on this project's own
data rather than asserted.

## A wrong filter is worse than no filter

Substituting `gemini-flash-lite-latest` for `gemini-2.5-flash` — done to work around the
quota limit below — dropped **Recall@1 from 0.947 to 0.789, beneath the dense-only
baseline.** Three rows that were rank 1 fell to ranks 3, 5 and 5.

The soft-filter design bounds this but does not remove it: a mismatching document is
demoted by `FILTER_BONUS`, so a *wrong* extraction actively pushes the correct answer
down. A strict filter would have removed it entirely, which is worse, but "soft" is not
"safe".

Two consequences worth carrying:

- **The extractor model is part of the measurement.** Changing it changes the result, so
  it is pinned in config with this note attached.
- Switching models to dodge a quota limit silently changed what was being measured. The
  contaminated run is preserved at `data/eval-runs/20260824T200831-stage1.md`.

## Budget — the binding constraint

Measured against the live API, not read from documentation:

| quota | limit | stage 1 eval cost | ingest cost |
|---|---|---|---|
| `generate_content_free_tier_requests` | **20 / day / model** | **21 per run** | 0 |
| `embed_content_free_tier_requests` | 1000 / day | 21 per run | ~377 |

**A single 21-query stage-1 evaluation does not fit in one day's generate budget.** Not
"fewer than three runs" — fewer than one. Embeddings are not the constraint; generation is,
by a factor of twenty.

The fix is the stage 1 cache (`STAGE1_CACHE=true`), keyed on **query text and the system
prompt and the model**. The gold set runs the same 21 strings forever, so a warm cache
makes repeat runs cost zero generate calls, and the embed budget then allows roughly 47
evaluations a day. Changing the prompt or the model invalidates every entry, which is
correct: keying on the query alone would serve stale extractions after a prompt change and
the run would look fine while measuring the previous prompt.

A cold run still needs 21 calls against a 20/day limit, so the first population of the
cache has to span two days or use a second model deliberately and be discarded as a
measurement.

## What the ceiling means for the product, not just the eval

**20 generate calls per day, per model. Stage 1 is one call per search. So the current
design supports 20 user searches per day, in total, across all users.**

That is not an evaluation inconvenience. It is the product's throughput.

**Is it survivable for the defence demo?** Probably, narrowly. A demo is five to ten
searches. But the failure mode is specific and worth naming: **rehearsing on the morning
of the demo can exhaust the day's budget before the demo happens.** The quota is daily and
per project, not per session. If it runs out mid-demo, stage 1 fails silently to
passthrough and the system quietly reverts to the dense-only baseline — the calendar
starts winning again, live, and nothing on screen says why.

Options, with the numbers actually measured. Not a recommendation.

**A — paid tier.** Removes the cap. Stage 1 prompts are small: a ~400-token system prompt
plus a short query, so a full 21-query evaluation is on the order of ten thousand tokens.
The volume is tiny; current per-token pricing needs checking rather than quoting from
memory. Cost: money, and a card on file.

**B — a cheaper model for stage 1 only. Measured, and strictly worse than not doing it.**
`gemini-flash-lite-latest` produced Recall@1 0.789 against 0.947 for the pinned model —
and 0.789 is *below* the 0.842 dense-only baseline. A weaker extractor produces wrong
filters, and a wrong filter demotes the correct answer. This is not a trade-off with a
cost; it is dominated. It also does not raise the ceiling much, because the quota is
per-model: four models is 80 calls a day, which is a workaround rather than an
architecture.

**C — skip stage 1 when the query carries no filterable signal.** Measured on the cached
extractions: **4 of 18 queries produced no usable filter at all** — 22% of calls wasted.
Skipping those would raise the effective ceiling from 20 to roughly 25 searches a day. The
catch is that you cannot know a query has no signal without asking, so it needs a local
heuristic — source-type words, person names, date phrases — and a wrong prediction loses
the filter for a query that needed one. Built in phase 3c; see `PHASE3C.md`.

> **Correction, 2026-08-25.** This paragraph first said *7 of 18* and *39%*, projecting a
> ceiling of ~33 searches a day. Both numbers were wrong. Recounted directly — treating
> any of `source_types` / `sender` / `entities` / `after` / `before` as a usable filter —
> the empty extractions are **q002, q003, q004, q014: 4 of 18**.
>
> A second problem sits underneath the first. **Every one of the 18 cached extractions
> keys against `gemini-flash-lite-latest`, not the pinned `gemini-2.5-flash`** — the
> rejected model from the section above. So the count describes the extractor this
> project does not use, and a weaker extractor finds *fewer* filters than the pinned one
> would. 22% is therefore an upper bound on what skipping could save.
>
> The real gain is five extra searches a day or fewer, against the risk of losing a
> filter. That is a materially worse trade than the one option C was chosen on.

**D — accept the cap.** 20 searches a day. Adequate for a demo, not for development, and
not for anyone actually using it. Free.

**E — a local model for stage 1.** Removes the quota entirely and strengthens the privacy
claim, since the query would stop leaving the machine at all. But result B is the warning:
a weaker extractor was worse than no extractor, and a small local model is likely weaker
than `gemini-2.5-flash`. High risk on the evidence available.

**The refusal implication.** If refusal needs a second generate call per query, the
ceiling halves to **10 searches a day**. Any refusal design has to state its call cost
before it is built, not after.

## Stage 1 latency

- `gemini-2.5-flash`: 2.2 s – 3.0 s per query
- `gemini-flash-lite-latest`: median 973 ms, range 272 – 1609 ms

Retrieval itself is tens of milliseconds, so search latency goes from ~0.05 s to ~3 s.
**Caching fixes the evaluation loop, not real use** — a first-time query still pays the
call. That is a genuine trade-off for the report, not a bug. Untested mitigations: skip
stage 1 when the query carries no filterable signal, or run it concurrently with the
unfiltered search and apply boosts when it returns.

## Refusal is not a threshold problem

Refusal accuracy stayed at 0.000, as predicted, and the distribution explains why no
threshold fixes it:

```
0.538  q020  must_refuse      ← lowest score in the set
...
0.647  q021  must_refuse      ← above NINE correct answers
...
0.775  q005  content_semantic
```

q020 ("my passport") is separable. q021 ("my college fee receipt") is not: catching it
would mean refusing eight correct answers. The calendar genuinely contains events about
college and fees, so the similarity is real. **Absence is not low similarity.**

Refusal needs a different signal. Most promising: **document-type agreement** — stage 1
extracts `document_type: receipt`, nothing in the corpus is a receipt, refuse regardless
of score. That tests the same thing the user asked, rather than a proxy for it.

## Known limitations, unchanged

- `document_identity` unmeasured: no ID-card photo in the corpus.
- Three corpus files contain no extractable text and are unfindable by any query.
- Tesseract is the only working OCR engine on this hardware.
- 19 retrieval rows means one row is 0.053 of Recall@1. Read the counts, not the
  fractions, and do not read significance into a difference of one.

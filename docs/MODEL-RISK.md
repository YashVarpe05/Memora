# Model risk — every stage 1 number depends on a model that is closing

Written 2026-08-26, before it becomes urgent. Deliberately not written under pressure.

## The finding

`gemini-2.5-flash` — the model this project pins, and the one every stage 1 measurement
was taken with — **is closed to new users.** Measured directly, not read from a
changelog:

| model | key created before the cutoff | key created after |
|---|---|---|
| `gemini-2.5-flash` | **200 OK** | **404** — *"no longer available to new users"* |
| `gemini-3.6-flash` | 200 OK | 200 OK |
| `gemini-embedding-001` | 200 OK | 200 OK |

Both keys are valid and on the same account. The only difference is when the project
behind each was created. Access is an accident of timing, and it is not renewable — a
replacement key issued today cannot reach the model.

**`models.list` returns `gemini-2.5-flash` for both keys.** Listing is not access; only
the call reveals the difference. That is the third instance of this shape in this repo,
after PaddleOCR importing without running and the eval guard that only fired at 100%.

## Blast radius, scoped by measurement

Not everything is exposed. The important scoping is that **only generation is affected**:

| artefact | depends on | survives a forced migration? |
|---|---|---|
| `BASELINE.md` (dense-only, 0.842) | embeddings only, **no generate call** | **yes** |
| The 377 stored chunk vectors | `gemini-embedding-001`, reachable by both keys | **yes** |
| CLIP image vectors and fusion | local model, no API at all | **yes, unconditionally** |
| `PHASE3.md` (0.947) | stage 1 on `gemini-2.5-flash` | **no** |
| `PHASE3C.md` (skip arm) | stage 1 | **no** |
| `PHASE3C-NOSKIP.md` (falsifier) | stage 1 | **no** |
| `PHASE3D.md` (screenshot fix) | stage 1 | **no** |

So the corpus does not need re-ingesting and the baseline does not need re-running. What
would be lost is **the entire stage 1 half of the ablation** — which is the project's
contribution.

## What a forced migration costs, counted

The stage 1 cache keys on **model + prompt + query**, so a model change invalidates every
entry by design. Counting the gold set as it stands (23 rows, 8 skipped by the signal
heuristic):

| step | calls |
|---|---|
| Re-populate all 23 queries under the new model | **23** |
| Both arms then read from cache | 0 |
| **Total** | **23** |

**At the measured free-tier ceiling of 20 generate requests per day per model per project,
that is two days** — one to warm 20, one for the remainder plus the runs. Add a third if
anything fails, which on current evidence it will.

Embeddings are not a constraint: 23 queries against a 1000/day limit.

**This is cheap in calls and expensive in comparability.** The numbers would be
internally consistent afterwards, and **not comparable to anything published before the
migration.** `PHASE3.md` already measured what changing the extractor does —
`gemini-flash-lite-latest` scored Recall@1 0.789, *below* the 0.842 achieved by using no
extractor at all. A different model is a different system, not a different version of the
same one.

## The reproducibility limitation, stated plainly

**An examiner or reader with a new API key cannot reproduce the stage 1 numbers in this
project, because they cannot access the model those numbers were taken with.**

That is a real bound on the work. It is better stated in the report than discovered by
someone who tries. The precise form:

> Stage 1 results were measured on `gemini-2.5-flash`. That model has since been closed
> to new API projects, so reproducing these figures requires a project created before the
> cutoff. The dense-only baseline, the corpus vectors and all visual-search results are
> unaffected and reproduce from any key.

**What reproduces regardless:** the baseline, the corpus, CLIP, the fusion, the whole
architecture, and every structural claim about RLS, masking and layer-one isolation. The
narrow non-reproducible part is the ablation *magnitude* — 0.842 → 0.947.

## What the report should say, in each case

**If migration is forced before submission.** Re-measure, publish the new numbers as the
headline, and keep the old table beside it as a labelled second column: *"measured on
`gemini-2.5-flash` before it was withdrawn"*. Do not delete the old numbers — a model
change moving Recall@1 is itself a finding, and it is the same finding flash-lite already
demonstrated at smaller scale. The ablation's *shape* surviving a model change would be a
stronger result than the original number.

**If it holds until submission.** Publish as is, with the limitation paragraph above in
the evaluation chapter rather than buried. State that access was verified on 2026-08-26
and is not renewable.

**Either way, do not quietly re-run and replace.** Every number in this project is dated
and attributed to a model; that discipline is what makes the ablation trustworthy, and
abandoning it at the last step to make a table look tidy would undo it.

## The mitigation is already planned, and it was planned for another reason

`PRODUCT.md` novelty claim 2 lists **fully-local stage 1** as future work, justified on
privacy: it would stop the query leaving the device at all.

**It is also the only version of this system whose results stay reproducible.** A model
that runs on the project's own hardware, with weights pinned by hash, cannot be withdrawn,
deprecated, silently updated, or gated behind a project-creation date. Anyone with the
repo could reproduce the numbers in five years.

That connection is worth making explicit in the report, because it turns a privacy
argument into a methodological one:

> Local inference is usually argued for on privacy grounds. This project encountered the
> other reason: a hosted model was withdrawn from new users mid-project, making the
> measurements taken against it unreproducible for anyone who had not already been granted
> access. Local weights are the only configuration in which a published number remains
> checkable.

**The obstacle remains measured and unchanged.** `PHASE3.md` records that a weaker
extractor scored *below* using no extractor at all, so a small local model is a real risk
rather than an obvious win. The honest position is that local stage 1 solves both privacy
and reproducibility **if** it can match extraction quality, and that is unproven.

CLIP is the existence proof for the easier half: it already runs locally, cost no quota,
and its results are reproducible by anyone with the repo.

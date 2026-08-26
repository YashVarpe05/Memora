# Local stage 1 — two 3B models, identical scores, disjoint competencies

Measured 2026-08-26 against the same corpus and gold set as every other arm. Full runs in
`LOCAL-QWEN.md` and `LOCAL-LLAMA.md`; predictions in `prompts/local-stage1.md`, written
before Ollama was installed.

## The finding

**Two 3B models scored exactly the same and failed on opposite rows.**

| row | qwen2.5:3b | llama3.2:3b | what the row needs |
|---|---|---|---|
| **q006** "the mail yash sent to rutuja" | **rank 1** | **rank 7** | the counter-intuitive rule that a scanned email is `pdf`, not `email` |
| **q016** "what i had planned to learn last year" | **rank 10** | **rank 1** | relative date arithmetic against a supplied current date |
| every other row | identical | identical | |

Both land on **Recall@1 0.895**. The score is the number attached to the finding, not the
finding.

**An aggregate metric called these two systems equivalent. They are not remotely
equivalent.** One can follow a counter-intuitive instruction and cannot do arithmetic; the
other can do the arithmetic and ignores the instruction. Substituting one for the other
changes *which queries work* while leaving every summary statistic untouched.

That generalises past this project. A benchmark reporting a single number for "small
models on structured extraction" would report these two as interchangeable, and a system
built on that conclusion would break on a query distribution weighted differently from the
gold set.

### The prediction was wrong in both directions at once

`prompts/local-stage1.md` named q006 the **highest** risk and q016 **moderate**, before
either model ran:

| row | predicted | qwen | llama |
|---|---|---|---|
| q006 | highest risk | **held** — prediction wrong | **failed** — prediction right |
| q016 | moderate risk | **failed** — prediction right | **held** — prediction wrong |

Every individual prediction was simultaneously right and wrong depending on which model
ran, because **the prediction was about "small models" as a category.** The category does
not behave uniformly, and a risk table written against it cannot be right.

This is the sharpest form of a lesson this project keeps producing in other shapes: the
aggregate hides the mechanism. Pre-registration caught it here only because the
predictions were per-row.

## The number, in context

| arm | model | Recall@1 | notes |
|---|---|---|---|
| dense-only | none | 0.842 | **the bar** |
| **local** | qwen2.5:3b-instruct | **0.895** | CPU, no quota, nothing leaves the machine |
| **local** | llama3.2:3b | **0.895** | same |
| hosted, old prompt | gemini-2.5-flash | 0.842 | `PHASE3C.md` |
| hosted, new prompt | gemini-2.5-flash | pending | `PHASE3D.md`, blocked |
| rejected | gemini-flash-lite | 0.789 | *below* using no extractor at all |

**The bar was 0.842, not 0.947.** `PHASE3.md` measured that a weak extractor scores below
using none, because a wrong filter actively demotes the right answer. Clearing 0.842 means
local stage 1 is worth having; matching 0.947 was the stretch and neither model reached it.

**Zero extraction failures across 23 queries, on both models.** Constrained JSON decoding
eliminated the malformed-output failure class entirely. That is the answer to the open
question from `PHASE3.md`: stage 1 is *structured extraction*, not reasoning, and it is a
genuinely different task from the one flash-lite was failing at — flash-lite's failures
were wrong content, not invalid output.

## The union: an observation, explicitly not a design

Neither model alone reaches hosted's predicted 0.947. But **no single row defeats both** —
q006 and q016 are covered between them, so a system that consulted both would score 19/19
on the two rows that separate them.

**This is recorded as an observation and must not be built.**

Routing between two extractors, or merging their outputs, is **a second classifier** — and
this project has already measured what a wrong classifier costs. `PHASE3.md`: substituting
`gemini-flash-lite-latest` produced Recall@1 0.789, *below* the 0.842 achieved by using no
extractor at all, because a wrong filter demotes the correct answer. A router that picks
the wrong model for a query does exactly that, and it does it with an extra failure mode
and double the latency — 15 s per query instead of 7.5 s.

**Future work, with the obstacle attached:** an ensemble is worth measuring only if the
routing decision can be made *without* a model — from the query string, the way
`query_signal.py` decides whether to call stage 1 at all. "This query contains a relative
date, so use the model that can do arithmetic" is a local, zero-cost, inspectable rule.
"Ask a classifier which model to trust" is the thing that already measured worse than
nothing.

## Why this matters beyond the score

Free-only is a project constraint, and local stage 1 is the only extractor configuration
with **no ceiling of any kind**:

| | hosted free tier | local |
|---|---|---|
| daily cap | 20/day/model | none |
| deprecation | live — see `MODEL-RISK.md` | none |
| query leaves the device | yes | **no** |
| reproducible from the repo | needs a pre-cutoff key | **yes** |

`MODEL-RISK.md` records the reproducibility half: `gemini-2.5-flash` is already closed to
new users, so every hosted number here is unreproducible for anyone without a pre-cutoff
key. Local weights cannot be withdrawn, deprecated, or gated behind a project creation
date.

**The claim, now measured rather than hoped for: the whole system runs on hardware the
user owns, with no external dependency and nothing leaving the device, and it costs one
row.**

## Cost

| | per query |
|---|---|
| local, warm | ~7.5 s |
| local, first call after container start | 89 s — model load |
| hosted | 2–3 s |

Three times slower, and the search UI already absorbs it: dense results paint in ~50 ms
and re-rank when stage 1 lands. A slow extractor degrades into the arm that already works
— the same property that makes a *failed* extractor safe.

## Limits

- **One corpus, 23 queries, one seed.** Deterministic (`temperature=0`, fixed seed) so it
  reproduces, but two rows of difference between two models is a direction, not a
  distribution.
- **Hosted under the same prompt is unmeasured.** `PHASE3D.md` is the only clean
  model-to-model comparison and is blocked on quota.
- **`sender` extraction is systematically weak** in qwen — missed on q012 and q013, where
  the query literally reads "from aradhana". The field is optional in the JSON schema and
  small models skip optional fields. Not tuned before measuring, deliberately; making it
  required after seeing the result would be fitting the method to the answer.

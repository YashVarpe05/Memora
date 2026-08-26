# Local stage 1 — the only configuration with no ceiling

**Predictions recorded before Ollama is installed. Nothing below was written after seeing
a result.**

## Why this moved from finale to load-bearing

Free-only is now a project constraint. Under it, local stage 1 is the only configuration
with **no ceiling of any kind**:

| | hosted free tier | multi-provider fallback | local |
|---|---|---|---|
| daily request cap | 20/day/model | 3 × small caps | **none** |
| deprecation risk | live — `gemini-2.5-flash` is already closed to new users | ×3 | **none** |
| query leaves the device | yes | yes, to three parties | **no** |
| reproducible from the repo | no — needs a pre-cutoff key | no | **yes** |

Multi-provider fallback buys three metered, deprecable, outbound dependencies instead of
one. More engineering for a weaker result. It is not planned.

## The bar is 0.842, not 0.947

`BASELINE.md` measures dense-only retrieval at **Recall@1 0.842**. `PHASE3.md` measures
hosted stage 1 at 0.947.

**0.842 is the bar**, because `PHASE3.md` already measured what a weak extractor does:
`gemini-flash-lite-latest` scored **0.789 — below using no extractor at all.** A wrong
filter actively demotes the right answer. So:

- **≥ 0.842** — local stage 1 is worth having. Removes every ceiling above.
- **0.842 – 0.947** — worth having, with an honest quality cost stated.
- **< 0.842** — **report it and stop.** Below baseline means the extractor is harmful, and
  the correct action is to delete the arm, not to iterate on prompts until it passes. That
  is the outcome flash-lite already produced once, and iterating it away would be fitting
  the method to the desired answer.

## Why this might work where flash-lite did not

Not optimism — a difference in the task. **Stage 1 is structured extraction, not
reasoning.** It fills a fixed JSON schema from one short sentence. Small instruct models
with *constrained decoding* — where the decoder can only emit tokens valid under the
schema — are far stronger at that than at open-ended generation, and the failure mode
flash-lite exhibited was wrong *content*, not malformed output.

Constrained decoding removes an entire failure class (unparseable JSON, invented fields)
that the hosted path handles with a `passthrough()` fallback. It cannot fix a wrong
`source_types` guess.

## Setup

Ollama in a container beside OCR. Same pattern: heavy local models live in containers, the
API talks HTTP, and a protocol keeps tests off the network.

| model | params | quantised size | why |
|---|---|---|---|
| `qwen2.5:3b-instruct` | 3B | ~2 GB | strongest small model at structured output |
| `llama3.2:3b-instruct` | 3B | ~2 GB | the obvious comparison |

CPU only. No GPU exists here and none will exist on a phone.

**Same `SYSTEM_PROMPT`, unchanged.** Rewriting the prompt for the local model would make
the arms measure two things at once, and the point is to isolate the extractor.

## Arms

| arm | stage 1 | status |
|---|---|---|
| dense-only | none | **measured, 0.842** |
| hosted | `gemini-2.5-flash` | **measured, 0.947** |
| local qwen | `qwen2.5:3b` | to run |
| local llama | `llama3.2:3b` | to run |

Two of four already exist, so this costs no Gemini quota at all.

### A sequencing constraint that would silently invalidate everything

**`image_embeddings` is currently empty — 0 rows — so CLIP fusion is a no-op.** That is
the only reason a run today is comparable to 0.842 and 0.947, which were both measured
before CLIP existed.

**Do not re-ingest the corpus with CLIP until this arm is measured.** Doing so adds a
second retrieval list to every query and makes the comparison meaningless, with no error
and no symptom — the numbers would simply stop meaning what the older ones mean.

## Predictions

| # | prediction | confidence |
|---|---|---|
| 1 | **Both local models produce valid JSON on ≥ 22 of 23 queries**, because constrained decoding makes malformed output nearly impossible | high |
| 2 | **Qwen ≥ Llama** on Recall@1 | moderate |
| 3 | **The better local model lands between 0.789 and 0.947** — above flash-lite, below hosted | moderate |
| 4 | **Recall@1 ≥ 0.842 for at least one local model** — clearing the bar | **50/50, genuinely unknown** |
| 5 | **CPU latency 5–20 s per query**, far worse than hosted's 2–3 s | high |
| 6 | The 8 skipped rows are **byte-identical across all arms** | near-certain — see the control |

### Where local extraction will fail, named in advance

| row | risk | why |
|---|---|---|
| **q006** "the mail yash sent to rutuja" | **highest** | needs the counter-intuitive rule that a scanned email is `pdf`, not `email`. A small model will read "mail" and emit `email` alone, and the answer is `mail.pdf` |
| **q010, q012** | high | the screenshot rule, which the hosted model only learned after an explicit prompt sentence. These are the rows phase 3d exists for |
| **q016** "last year" | moderate | relative date arithmetic against a supplied current date is exactly what small models get wrong |
| **q013, q009** | low | `sender` from "from aradhana" is the easiest possible extraction |

### The control that must not improve

**The 8 rows skipped by the signal heuristic: q002, q003, q004, q005, q011, q015, q020,
q021.**

They never reach stage 1 in any arm, so they must be **identical across all four arms —
same rank, same top result**. This is a structural control, not a statistical one.

- **All 8 identical:** the arm isolates stage 1, as intended.
- **Any of them moves:** the arms differ by something other than the extractor, and no
  comparison in this document means anything. Stop and find it before reading a number.

That control caught nothing in phase 3c, where all 21 rows matched exactly. It is cheap
and it is the reason the phase 3c result was trustworthy.

## What gets reported either way

**A below-baseline result is a publishable finding, not a failure.** "Small local models
cannot do query understanding well enough to beat doing nothing" is a concrete, measured
answer to a question the field asks loosely, and it makes the hosted dependency an
argued choice rather than an unexamined default.

Latency is reported separately from quality. If local stage 1 is accurate but takes 15 s,
that is a different trade-off from an inaccurate one — and the search UI already handles
it: dense results paint in ~50 ms and re-rank when stage 1 lands, so a slow local
extractor degrades into the arm that already works.

## Checks

```
cd apps/api && uv run pytest && uv run ruff check .
cd apps/api && uv run python -m memora.eval.baseline --stage1-provider=ollama --model=qwen2.5:3b --out docs/LOCAL-QWEN.md
```

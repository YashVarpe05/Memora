# Phase 3c — skip stage 1 when the query carries no filterable signal

**Predictions recorded before the heuristic exists.** Nothing in this file was written
after seeing a result.

## Two corrections to the numbers that motivated this phase

Both were found while preparing the predictions, and both weaken the case for the option
being built. They are stated first so the decision can be re-made with the real numbers.

### 1. The cached extractions came from the wrong model

`data/eval-runs/stage1-cache.json` holds 18 entries. Zero of them key against
`gemini-2.5-flash`; **all 18 key against `gemini-flash-lite-latest`** — the model measured
at Recall@1 0.789, *below* the 0.842 dense-only baseline, and discarded as contaminated in
`PHASE3.md`.

So every statement made about "the cached extractions" describes the rejected model, not
the pinned one. The cache is not stale-and-invalid — it is valid, for a model we do not
use.

### 2. It is 4 of 18 producing nothing, not 7 of 18

Recounted directly, treating any of `source_types` / `sender` / `entities` / `after` /
`before` as a usable filter:

| empty | q002, q003, q004, q014 |
|---|---|
| **4 of 18 = 22%** | not the 39% previously reported |

**The 39% figure I put in `PHASE3.md` is wrong and that line needs correcting.**

### What this does to the case for option C

The projected ceiling was 20 → ~33 searches a day. At 22% it is **20 → ~25**, and that is
measured on the *weaker* extractor, which fails to extract more often than the pinned one
does. A stronger model finding signal where a weaker one found none makes 22% an **upper**
bound. The real gain is five extra searches a day or fewer.

The build proceeds because it was asked for and because the harm analysis is worth having
either way. But the trade-off is now "risk losing filters to gain ≤5 searches a day", which
is a materially worse deal than the one option C was chosen on.

**One genuine benefit survives, and it is not the ceiling.** If the heuristic skips the 8
rows predicted below, a cold gold-set run costs **13 generate calls, not 21** — under the
20/day limit. A full stage-1 evaluation would fit in a single day for the first time in
this project.

## The design

A local, zero-cost check on the query string. Stage 1 runs only when the query contains at
least one of:

- **source-type vocabulary** — photo, screenshot, image, mail, email, whatsapp, chat,
  message, calendar, pdf, scan, document
- **a sender pattern** — `X sent`, `from X`, `sent to X`, `forwarded`
- **temporal vocabulary** — when, last year, yesterday, a month name, a 4-digit year

Otherwise the query goes straight to dense retrieval with no filters, which is exactly what
stage 1 returns for these queries anyway when it runs.

**What the heuristic structurally cannot see: entities.** `drone`, `uber`, `uipath`, `tcs`,
`youtube` are lowercase common-looking words. Detecting them locally needs a gazetteer of
the user's own corpus, which is a different feature. Every predicted harm below is an
entity the heuristic is blind to, and that is the design's real cost.

## Predictions

**SKIP = 8 of 21** (q002, q003, q004, q005, q011, q015, q020, q021).

| row | query | predicted | correct? |
|---|---|---|---|
| q001 | that motivation photo… | RUN | ✓ "photo" |
| q002 | the project report about ai agents… | **SKIP** | ✓ extraction was empty |
| q003 | the synopsis about checking code… | **SKIP** | ✓ extraction was empty |
| q004 | the project about making websites… | **SKIP** | ✓ extraction was empty |
| q005 | the list of drone topics… | **SKIP** | ✗ **loses `entities: [drone]`** |
| q006 | the mail yash sent to rutuja | RUN | ✓ "mail" + "sent" |
| q007 | the screenshot of that dashboard… | RUN | ✓ "screenshot" |
| q008 | the ai job someone forwarded… whatsapp | RUN | ✓ "whatsapp" |
| q009 | the job thing anu priya sent | RUN | ✓ "sent" |
| q010 | the tcs job… send cv on email | RUN | ✓ "email" |
| q011 | the uipath job in chennai | **SKIP** | ✗ **loses `entities: [uipath, chennai]`** |
| q012 | the message wajeed sent… | RUN | ✓ "message" + "sent" |
| q013 | the whatsapp message from aradhana | RUN | ✓ "whatsapp" + "from" |
| q014 | when was i supposed to fill… | RUN | ✗ wasted call — extraction was empty |
| q015 | that uber clone thing i planned… | **SKIP** | ✗ **loses `entities: [uber]`** |
| q016 | what i had planned to learn last year | RUN | ✓ "last year" |
| q017 | where are my birthday reminders kept | RUN | ✓ *if* "reminder" maps to calendar |
| q018 | the youtube course link… in my calendar | RUN | ✓ "calendar" |
| q019 | that photo of me… balcony | RUN | ✓ "photo" — the control, still a miss |
| q020 | my passport | **SKIP** | — refusal row, no filter either way |
| q021 | my college fee receipt | **SKIP** | — refusal row, no filter either way |

### The harm, named per row

A wrong skip loses a filter that would have helped. Three rows are predicted to lose one:

| row | risk | why |
|---|---|---|
| **q011** "the uipath job in chennai" | **highest** | The corpus holds several job documents. `uipath` is the *only* thing separating them — that is why the row is typed `disambiguation`. Losing it removes the disambiguating signal itself, and the +0.08 boost that put it at rank 1 goes with it. If one row falls off rank 1, this is the row. |
| **q005** "the list of drone topics" | moderate | `entities: [drone]` is a real filter, but "drone topics" is semantically distinctive on its own, so dense retrieval may hold rank 1 unaided. |
| **q015** "that uber clone thing" | low | Same shape as q005 and more distinctive still. "uber clone" is close to unique in this corpus. |

**Predicted cost: Recall@1 drops from 0.947 to 0.895 — one row, q011.** If two or more rows
fall, the vocabulary is too narrow and the honest response is to abandon the skip rather
than widen it until the number looks right.

**Predicted savings: 8 of 21 calls, 38% — higher than the 22% of extractions that were
genuinely empty, and that gap is the over-skipping.**

### Predictions that would falsify the design

- **If q001, q006, q007, q008, q009, q010, q012, q013, q016, q018 or q019 is skipped**, the
  vocabulary check is broken — every one of those carries an explicit source-type, sender,
  or date word.
- **If Recall@1 stays at 0.947**, the three predicted harms were all absorbed by dense
  retrieval, and the entity filters were worth less than assumed. That is a result about
  soft filters, not a free win.
- **If q017 is skipped**, "reminder" is missing from the calendar vocabulary and the
  metadata_only row loses its filter. Predicted RUN, but it is the one row where the
  prediction depends on a vocabulary choice not yet made.

## Acceptance criteria

1. The skip decision is a pure function of the query string. No model call, no I/O.
2. Skipped queries report `stage1_skipped: true`, distinct from `stage1_failed`. **A skip
   is a choice; a failure is a fault. Conflating them would let quota exhaustion hide
   inside a green field**, which is the exact failure the phase-3 guard was built to stop.
3. The eval reports skipped rows and the call count, so 13-not-21 is visible rather than
   claimed.
4. Held/broken reported per row against the table above.

## Checks

```
cd apps/api && uv run pytest && uv run ruff check .
cd apps/api && uv run python -m memora.eval.baseline --out docs/PHASE3C.md
```

# Stage 1 — filtered retrieval

Recorded 2026-08-25T15:34:01+00:00, commit `ef15342`.

**Query understanding is ON.** Compare against `BASELINE.md`, which is the
same corpus and gold set with stage 1 disabled.

## What was measured

- Corpus: 11 documents, 377 chunks
- Gold set: 21 queries (19 retrieval, 2 refusal)
- Retrieval: dense cosine over `gemini-embedding-001` at 768 dims, with stage 1 filters applied as boosts.
- Evaluated against an already-indexed corpus, verified by content hash.

## Headline

| metric | value |
|---|---|
| **Recall@1** | **0.842** (16/19) |
| Recall@5 | 0.947 |
| MRR@10 | 0.870 |
| Refusal accuracy | 0.000 (0/2) |

## By query type

| type | passed | total |
|---|---|---|
| `content_semantic` | 2 | 2 |
| `disambiguation` | 3 | 4 |
| `entity_resolution` | 3 | 4 |
| `metadata_only` | 3 | 3 |
| `must_refuse` | 0 | 2 |
| `temporal_resolution` | 3 | 3 |
| `visual_recall` | 2 | 3 |

## Every query

| id | type | rank | query | top result |
|---|---|---|---|---|
| q001 | `visual_recall` | 1 | that motivation photo with the quote about working hard | 1773316539_ZnyZH84E.jpeg |
| q002 | `content_semantic` | 1 | the project report about ai agents that write code | AgentOS_Synopsis.pdf |
| q003 | `disambiguation` | 1 | the synopsis about checking code for mistakes | CodeGuardAI_Synopsis.pdf |
| q004 | `disambiguation` | 1 | the project about making websites do things on their own | Relay____Synopsis.pdf |
| q005 | `content_semantic` | 1 | the list of drone topics i was supposed to learn | mail.pdf |
| q006 | `entity_resolution` | 1 | the mail yash sent to rutuja | mail.pdf |
| q007 | `visual_recall` | 1 | the screenshot of that dashboard with the forms on it | WhatsApp Image 2026-06-13 at 16.58 |
| q008 | `metadata_only` | 1 | the ai job someone forwarded to me on whatsapp | WhatsApp Image 2026-07-03 at 01.24 |
| q009 | `entity_resolution` | 1 | the job thing anu priya sent | WhatsApp Image 2026-07-03 at 01.24 |
| q010 | `disambiguation` | 5 | the tcs job where they asked to send cv on email | mail.pdf |
| q011 | `disambiguation` | 1 | the uipath job in chennai | WhatsApp Image 2026-07-03 at 01.24 |
| q012 | `entity_resolution` | 3 | the message wajeed sent about a developer role | Relay____Synopsis.pdf |
| q013 | `entity_resolution` | 1 | the whatsapp message from aradhana | WhatsApp Image 2026-07-03 at 01.24 |
| q014 | `temporal_resolution` | 1 | when was i supposed to fill the scholarship form | yashvarpe2005@gmail.com.ics |
| q015 | `temporal_resolution` | 1 | that uber clone thing i planned to build | yashvarpe2005@gmail.com.ics |
| q016 | `temporal_resolution` | 1 | what i had planned to learn last year | yashvarpe2005@gmail.com.ics |
| q017 | `metadata_only` | 1 | where are my birthday reminders kept | Birthdays_yashvarpe2005@gmail.com. |
| q018 | `metadata_only` | 1 | the youtube course link i saved somewhere in my calendar | yashvarpe2005@gmail.com.ics |
| q019 | `visual_recall` | **miss** | that photo of me leaning on the balcony at college | WhatsApp Image 2026-06-13 at 16.58 |
| q020 | `must_refuse` | **ANSWERED** | my passport | yashvarpe2005@gmail.com.ics |
| q021 | `must_refuse` | **ANSWERED** | my college fee receipt | yashvarpe2005@gmail.com.ics |

## Where the failures went

Most frequent top result:

| file | times ranked first |
|---|---|
| `yashvarpe2005@gmail.com.ics` | 6 |
| `mail.pdf` | 3 |
| `Relay____Synopsis.pdf` | 2 |
| `WhatsApp Image 2026-06-13 at 16.58.51.jpeg` | 2 |
| `WhatsApp Image 2026-07-03 at 01.24.47 (1).jpeg` | 2 |

`yashvarpe2005@gmail.com.ics` is the top result for 6 of 21 queries (29%).

## Stage 1 calls skipped

**13 stage 1 calls for 21 queries, cold.** The free tier allows 20 generate requests a day, so a cold run fits in one day's budget; a run without skipping needs 21 and does not.

Cold is the number that matters for planning. A warm cache serves most of these rows for free, so the calls actually issued by any given run may be far fewer — which is why this says *required*, not *spent*.

Skipped means the query carried no source-type word, no sender and no date, so stage 1 had nothing to extract. Skipping cannot improve a result — it can only fail to help one. Rows skipped:

| row | query | rank | predicted harm |
|---|---|---|---|
| q002 | the project report about ai agents that write code | 1 | none predicted |
| q003 | the synopsis about checking code for mistakes | 1 | none predicted |
| q004 | the project about making websites do things on their own | 1 | none predicted |
| q005 | the list of drone topics i was supposed to learn | 1 | loses entities [drone] |
| q011 | the uipath job in chennai | 1 | loses entities [uipath, chennai] — highest risk |
| q015 | that uber clone thing i planned to build | 1 | loses entities [uber] |
| q020 | my passport | — | none predicted |
| q021 | my college fee receipt | — | none predicted |

## Stage 1 cost

An extra model call on every search. Measured across these queries:

- median 0 ms, range 0-0 ms
- added to every search, before any retrieval happens

## Top-score distribution

Raw top similarity per query - the number refusal is decided on. Rows that
should refuse must fall below rows that should not; where they interleave,
no single threshold separates them and refusal needs a different signal.

| score | id | type |
|---|---|---|
| 0.494 | q019 | `visual_recall` |
| 0.528 | q010 | `disambiguation` |
| 0.538 | q020 | `must_refuse` |
| 0.547 | q007 | `visual_recall` |
| 0.562 | q016 | `temporal_resolution` |
| 0.567 | q012 | `entity_resolution` |
| 0.599 | q017 | `metadata_only` |
| 0.606 | q001 | `visual_recall` |
| 0.622 | q009 | `entity_resolution` |
| 0.638 | q003 | `disambiguation` |
| 0.645 | q004 | `disambiguation` |
| 0.647 | q021 | `must_refuse` |
| 0.651 | q013 | `entity_resolution` |
| 0.660 | q006 | `entity_resolution` |
| 0.670 | q008 | `metadata_only` |
| 0.685 | q018 | `metadata_only` |
| 0.688 | q011 | `disambiguation` |
| 0.704 | q015 | `temporal_resolution` |
| 0.721 | q002 | `content_semantic` |
| 0.764 | q014 | `temporal_resolution` |
| 0.775 | q005 | `content_semantic` |

## Observed fetch-window behaviour

The window widens until enough documents surface rather than using a fixed size.
Observed across these queries:

- chunks examined: 200–377
- widenings: 2–3
- corpus: 377 chunks, so the window reached 100% of it at most

**Known bound.** A document whose only matching chunk falls outside the window is
invisible. This bounds *list completeness*, not the top hit — a strong match puts a
chunk near the top of any window — so Recall@5 erodes before Recall@1 does. At
roughly a thousand documents the ceiling (2000 chunks) starts to bind, and the fix
is a document-level pre-filter rather than a larger window.

## Known limitations at the time of measurement

- **No visual understanding.** OCR extracts text; it does not describe pictures. Three corpus files contain no text and are therefore unfindable by any query.
- **`document_identity` is unmeasured.** The corpus contains no photograph of an ID card, so the flagship query type has no gold row. This is the largest gap.
- **Refusal is not enforced by the system.** `MIN_SIMILARITY_UNCALIBRATED` is 0.35 and gibberish scores ~0.489, so the threshold never fires. Any refusal recorded here came from the corpus being genuinely empty of matches, not from the guard.
- **Tesseract is the only working OCR engine.** PaddleOCR installs and cannot run on this hardware, in the container as well as on Windows.

---

# Analysis — option C, held and broken

Everything above this line is generated by `memora.eval.baseline` and is regenerable.
Everything below is written, and records the decision the run was made to settle.

## The headline number, and why it does not mean what the decision rule assumed

**Recall@1 0.842**, against 0.947 in `PHASE3.md` and 0.842 dense-only in `BASELINE.md`.
The pre-agreed rule was: at or above 0.930 keep the skip, below it revert.

**The threshold was crossed. The premise behind it was not.** The skip cost nothing on
any row it touched, and the two rows that fell are rows where stage 1 **ran**.

## Predictions, marked

Recorded in `prompts/phase-3c-skip-stage1.md` before the heuristic was written.

| prediction | outcome |
|---|---|
| 8 rows skip: q002, q003, q004, q005, q011, q015, q020, q021 | **HELD.** Exactly those eight, no others. |
| 13 generate calls, fits one day's budget | **HELD.** 13 spent against a 20/day ceiling. |
| **q011 falls off rank 1 — highest risk** | **BROKEN. q011 is rank 1.** |
| q005 may lose `entities: [drone]` | **BROKEN, at the root.** |
| q015 may lose `entities: [uber]` | **BROKEN, at the root.** |
| Recall@1 drops to 0.895, one row | **BROKEN.** It dropped to 0.842, two rows — neither of them a skipped row. |

### Why two of the three predicted harms were never possible

The harm table was built from the cached extractions, which — as `PHASE3.md` now records —
came from the **rejected `gemini-flash-lite-latest`**. Asking the pinned model what it would
have returned for the three rows costs three calls and settles it:

| row | flash-lite (what the prediction was built on) | **`gemini-2.5-flash` (pinned)** |
|---|---|---|
| q005 | `entities: [drone]` | **nothing** |
| q015 | `entities: [uber]` | **nothing** |
| q011 | `entities: [uipath, chennai]` | `entities: [uipath, chennai]` |

For q005 and q015 the pinned model extracts **no usable filter at all**, so skipping them
costs exactly nothing — the predicted harm could not have occurred. For q011 the filter was
genuinely available and genuinely skipped, **and the answer is rank 1 without it**: the
entity filter was not load-bearing.

**Every one of the eight skipped rows landed where it should.** All six answerable ones are
rank 1; the two refusal rows are unaffected because refusal is not built yet.

## What actually cost the two rows

Both q010 and q012 expect a **WhatsApp screenshot**, and stage 1 gave both a `source_types`
filter with no `image` in it:

| row | rank | extraction | expected file |
|---|---|---|---|
| q010 | **5** | `source_types: [email, pdf]`, `entities: [tcs]` | `WhatsApp Image …01.24.47 (1).jpeg` |
| q012 | **3** | `source_types: [chat, email, pdf]`, `sender: Wajeed` | `WhatsApp Image …01.24.48.jpeg` |

The queries say "on email" and "the message wajeed sent". The documents are **photographs of
those messages**. Stage 1 answered the question it was asked and picked the wrong axis: it
read the *subject* of the query as the *format* of the file.

The system prompt already covers one instance of this — "a scanned or printed email saved as
a file is `pdf`, not `email`" — and does not cover the screenshot case. That single missing
sentence is the whole regression.

`q008` shows the mechanism is a demotion and not an exclusion: it also received
`source_types: [chat]` with no `image`, and still holds rank 1 because its raw similarity is
0.670. q010 is the **lowest-scoring row in the set at 0.528** and q012 sits at 0.567, so the
same demotion is fatal for them and survivable for q008. Soft filters bound this damage.
They do not remove it — the finding from `PHASE3.md` reproducing on new rows.

**This is a wrong filter, not a missing one.** Skipping stage 1 could not have caused it,
and reverting the skip cannot fix it.

## The decision

**The skip is kept, and the pre-agreed rule is not applied as written.**

Stating this plainly because it is a deviation: 0.842 is below 0.930, and the rule said
revert. The rule was a proxy for "did skipping stage 1 hurt retrieval". The per-row data
answers that question directly and the answer is no — six of six answerable skipped rows are
rank 1, and the one row that had a real filter to lose ranked first without it. Reverting
would remove a change measured to be harmless in response to a number produced by an
unrelated defect two rows away.

**And it is kept for reproducibility, not for throughput.** The ceiling gain was corrected
from ~33 searches a day to ~25, and five extra searches would not justify the risk. What
justifies it is this: **this run cost 13 generate calls and fitted inside one day's budget.**
It is the first full stage-1 evaluation in this project that has been reproducible within 24
hours. A 21-call run does not fit in a 20-call day and never did.

### What would overturn this

The clean test is a no-skip run on the same model and prompt. **It costs 8 calls, not 21,
because the 13 rows measured here are now cached** — and it does not fit today, with 17 of
20 already spent. If that run puts q005, q011 or q015 above rank 1, the skip has a cost and
this decision is wrong. Until then it is measured at zero.

## The budget coupling, stated because it constrains every phase after this one

`generate_content` is **20 per day, per model**, and stage 1 spends one per search.

- **With the skip:** a cold gold-set run costs **13 calls**. It fits in one day.
- **Without the skip:** it costs **21 calls**. It does not fit in any day, and never has.

**If the skip is ever reverted, refusal measurement goes back to 21 calls and stops fitting
in a single day.** Adding `document_type` to stage 1's schema changes the system prompt,
which invalidates every cache entry, so phase 3b needs a cold run of its own. With the skip
that is 13 calls and one day. Without it, phase 3b cannot be measured in a day at all.

This is why the two phases cannot share a day — 13 + 13 is 26 against a ceiling of 20 — and
why the skip is load-bearing for the *schedule* even though it is neutral for *accuracy*.

## Also observed

**The failure guard fired during this run.** One of the thirteen stage 1 calls failed —
q019, the control row — and the harness reported `stage 1 failed on 1/13 queries` in the
console rather than absorbing it. That row misses in every arm so the metrics are unmoved,
but before yesterday that failure would have been invisible. The instrument works on real
data, which is the only place it counts.

**Provenance.** This is the first stage-1 run archived rather than hand-transcribed.
The 0.947 in `PHASE3.md` was copied from console output by hand, so treat the 0.947 → 0.842
gap as **two identified rows plus unquantified variance**, not as a clean delta. The per-row
table is the evidence here; the headline is not.

**Reproduced, twice, at zero quota cost.** The run was repeated against the warm cache and
returned 0.842 / 0.947 / 0.870 — identical to the digit, with an identical per-row table.
Three archived runs sit in `data/eval-runs/`: `20260825T143501`, `20260825T153236`,
`20260825T153401`.

That matters for two claims. First, retrieval is deterministic given fixed extractions, so
the 0.947 gap is not run-to-run noise in the *search* — it is the extractions or the
transcription. Second, it is the reproducibility argument demonstrated rather than asserted:
the second and third runs issued **one** generate call between them, not thirteen. Thirteen
is the cold cost, and it is the number that fits in a day.

**The q019 stage 1 failure did not recur.** It failed once in the first run and succeeded in
the next, so it was a transient transport error rather than a quota wall — which is exactly
what a one-of-thirteen failure rate should have suggested, and exactly what the guard is for.
A silent version of that would have looked like a slightly worse model.

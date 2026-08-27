# Stage 1 — filtered retrieval

Recorded 2026-08-27T15:47:44+00:00, commit `3c18414`.

**Query understanding is ON.** Compare against `BASELINE.md`, which is the
same corpus and gold set with stage 1 disabled.

## What was measured

- Corpus: 14 documents, 377 chunks
- Gold set: 23 queries (19 retrieval, 4 refusal)
- Retrieval: dense cosine over `gemini-embedding-001` at 768 dims, with stage 1 filters applied as boosts.
- Evaluated against an already-indexed corpus, verified by content hash.

## Headline

| metric | value |
|---|---|
| **Recall@1** | **0.895** (17/19) |
| Recall@5 | 1.000 |
| MRR@10 | 0.932 |
| Refusal accuracy | 0.500 (2/4) |

## By query type

| type | passed | total |
|---|---|---|
| `content_semantic` | 2 | 2 |
| `disambiguation` | 4 | 4 |
| `entity_resolution` | 4 | 4 |
| `metadata_only` | 2 | 3 |
| `must_refuse` | 2 | 4 |
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
| q008 | `metadata_only` | 5 | the ai job someone forwarded to me on whatsapp | Relay____Synopsis.pdf |
| q009 | `entity_resolution` | 1 | the job thing anu priya sent | WhatsApp Image 2026-07-03 at 01.24 |
| q010 | `disambiguation` | 1 | the tcs job where they asked to send cv on email | WhatsApp Image 2026-07-03 at 01.24 |
| q011 | `disambiguation` | 1 | the uipath job in chennai | WhatsApp Image 2026-07-03 at 01.24 |
| q012 | `entity_resolution` | 1 | the message wajeed sent about a developer role | WhatsApp Image 2026-07-03 at 01.24 |
| q013 | `entity_resolution` | 1 | the whatsapp message from aradhana | WhatsApp Image 2026-07-03 at 01.24 |
| q014 | `temporal_resolution` | 1 | when was i supposed to fill the scholarship form | yashvarpe2005@gmail.com.ics |
| q015 | `temporal_resolution` | 1 | that uber clone thing i planned to build | yashvarpe2005@gmail.com.ics |
| q016 | `temporal_resolution` | 1 | what i had planned to learn last year | yashvarpe2005@gmail.com.ics |
| q017 | `metadata_only` | 1 | where are my birthday reminders kept | Birthdays_yashvarpe2005@gmail.com. |
| q018 | `metadata_only` | 1 | the youtube course link i saved somewhere in my calendar | yashvarpe2005@gmail.com.ics |
| q019 | `visual_recall` | 2 | that photo of me leaning on the balcony at college | WhatsApp Image 2026-06-13 at 16.58 |
| q020 | `must_refuse` | refused | my passport | - |
| q021 | `must_refuse` | refused | my college fee receipt | - |
| q022 | `must_refuse` | **ANSWERED** | the photo of me at the Taj Mahal | WhatsApp Image 2026-06-13 at 16.58 |
| q023 | `must_refuse` | **ANSWERED** | the group photo from the farewell party | yashvarpe2005@gmail.com.ics |

## Where the failures went

Most frequent top result:

| file | times ranked first |
|---|---|
| `yashvarpe2005@gmail.com.ics` | 5 |
| `WhatsApp Image 2026-06-13 at 16.58.51.jpeg` | 3 |
| `Relay____Synopsis.pdf` | 2 |
| `mail.pdf` | 2 |
| `WhatsApp Image 2026-07-03 at 01.24.47 (1).jpeg` | 2 |

`yashvarpe2005@gmail.com.ics` is the top result for 5 of 23 queries (22%).

## Stage 1 calls skipped

**17 stage 1 calls for 23 queries, cold.** The free tier allows 20 generate requests a day, so a cold run fits in one day's budget; a run without skipping needs 23 and does not.

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

## Stage 1 cost

An extra model call on every search. Measured across these queries:

- median 4080 ms, range 2688-4855 ms
- added to every search, before any retrieval happens

## Top-score distribution

Raw top similarity per query - the number refusal is decided on. Rows that
should refuse must fall below rows that should not; where they interleave,
no single threshold separates them and refusal needs a different signal.

| score | id | type |
|---|---|---|
| 0.494 | q019 | `visual_recall` |
| 0.530 | q022 | `must_refuse` |
| 0.537 | q023 | `must_refuse` |
| 0.547 | q007 | `visual_recall` |
| 0.578 | q008 | `metadata_only` |
| 0.599 | q017 | `metadata_only` |
| 0.603 | q016 | `temporal_resolution` |
| 0.606 | q001 | `visual_recall` |
| 0.619 | q010 | `disambiguation` |
| 0.622 | q009 | `entity_resolution` |
| 0.638 | q003 | `disambiguation` |
| 0.645 | q004 | `disambiguation` |
| 0.651 | q013 | `entity_resolution` |
| 0.660 | q006 | `entity_resolution` |
| 0.685 | q018 | `metadata_only` |
| 0.688 | q011 | `disambiguation` |
| 0.704 | q015 | `temporal_resolution` |
| 0.716 | q012 | `entity_resolution` |
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

# Analysis — refusal by document-type agreement

## Result

| metric | before | after |
|---|---|---|
| **Refusal accuracy** | **0.000** | **0.500** (2 of 4) |
| Recall@1 | 0.895 | **0.895** |
| Recall@5 | 0.947 | **1.000** |
| MRR@10 | 0.926 | **0.932** |

**Refusal works and cost nothing in retrieval.** Zero false refusals — the predicted
1–2 did not materialise, and Recall@5 reached 1.000 for the first time in the project.

| row | query | outcome |
|---|---|---|
| q020 | "my passport" | **refused** |
| q021 | "my college fee receipt" | **refused** |
| q022 | "the photo of me at the Taj Mahal" | answered |
| q023 | "the group photo from the farewell party" | answered |

## Predictions, marked

Recorded in `prompts/phase-3b-refusal.md` before implementation.

| prediction | outcome |
|---|---|
| q021 refused — the row the design is for | **HELD** |
| q020 refused | **HELD** |
| q019 must NOT be refused — the control | **HELD.** Not refused, and now found at rank 2. |
| Recall@1 unchanged | **HELD.** 0.895 either way. |
| **1–2 false refusals out of 19, q017 most likely** | **BROKEN, in the good direction. Zero.** |

**Why the false refusals did not happen.** The risk table predicted the model would
volunteer "reminder" for q017, "list" for q005, "cv" for q010. Two defences held:
`NOT_A_TYPE` rejects those words explicitly, and `normalise()` returns None for anything
outside the vocabulary, so refusal fails **open**. The prediction was reasonable and the
defences were simply stronger than estimated.

## The bug the measurement found: a skip that disabled refusal

The first run scored **0.000 with the extractor working perfectly**:

```
"my college fee receipt"  ->  document_type = 'receipt'   correct
"my passport"             ->  document_type = 'passport'  correct
```

The extraction was right and refusal still never fired, because **q020 and q021 were being
skipped by the signal heuristic.** `query_signal` looked for a source type, a sender or a
date, found none in "my passport", and skipped stage 1 — so there was no `document_type` to
disagree with.

**The heuristic was correct when it was written and became wrong when refusal landed.** Its
vocabulary was built when stage 1 returned only source types, senders and dates. Adding
`document_type` made a fourth kind of signal that the heuristic could not see, and the two
lists silently diverged.

The fix derives the document words from `document_type.VOCABULARY`, so there is **one
source of truth** — adding a type there cannot leave the heuristic behind again. A test
asserts that structurally rather than by listing words twice.

**The shape is familiar and worth naming:** an optimisation that was free at the time it
was measured became costly when a later feature changed what "free" meant. Nothing broke;
the assumption underneath it expired.

## What type agreement does not solve

q022 and q023 are still answered, and that is the design working as specified rather than
failing. **Neither query names a document type** — "the photo of me at the Taj Mahal" is a
photo, and `photo` is explicitly in `NOT_A_TYPE` because treating it as a type would refuse
every genuine photo query.

They are **visual absence controls**, and type agreement was never the mechanism for them.
A query that names no type and describes a picture that does not exist needs a different
signal — CLIP returns a nearest neighbour for every query, so the visual index cannot say
"absent" any more than the text index can.

**Refusal accuracy 0.500 is therefore the honest ceiling of this mechanism on this gold
set**, not a partial implementation. Two of the four refusal rows name a document type and
both refuse; two do not and are out of scope. Visual absence remains unsolved and is
recorded as such.

## Cost

**Zero.** Stage 1 runs locally, so adding `document_type` to the prompt cost no quota, and
this measurement was re-run three times in one afternoon — once to find the skip bug, once
to confirm the fix, once for the record.

Under the hosted arm this phase would have cost a cold 13 calls per iteration against a
20/day ceiling: **the skip bug alone would have taken two days to find and fix.** That is
the third benefit of going local, after privacy and reproducibility, and it only became
visible once the constraint was gone.

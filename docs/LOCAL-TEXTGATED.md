# Stage 1 — filtered retrieval

Recorded 2026-08-27T15:25:40+00:00, commit `4977520`.

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
| Recall@5 | 0.947 |
| MRR@10 | 0.926 |
| Refusal accuracy | 0.000 (0/4) |

## By query type

| type | passed | total |
|---|---|---|
| `content_semantic` | 2 | 2 |
| `disambiguation` | 4 | 4 |
| `entity_resolution` | 4 | 4 |
| `metadata_only` | 3 | 3 |
| `must_refuse` | 0 | 4 |
| `temporal_resolution` | 2 | 3 |
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
| q010 | `disambiguation` | 1 | the tcs job where they asked to send cv on email | WhatsApp Image 2026-07-03 at 01.24 |
| q011 | `disambiguation` | 1 | the uipath job in chennai | WhatsApp Image 2026-07-03 at 01.24 |
| q012 | `entity_resolution` | 1 | the message wajeed sent about a developer role | WhatsApp Image 2026-07-03 at 01.24 |
| q013 | `entity_resolution` | 1 | the whatsapp message from aradhana | WhatsApp Image 2026-07-03 at 01.24 |
| q014 | `temporal_resolution` | 1 | when was i supposed to fill the scholarship form | yashvarpe2005@gmail.com.ics |
| q015 | `temporal_resolution` | 1 | that uber clone thing i planned to build | yashvarpe2005@gmail.com.ics |
| q016 | `temporal_resolution` | 10 | what i had planned to learn last year | mail.pdf |
| q017 | `metadata_only` | 1 | where are my birthday reminders kept | Birthdays_yashvarpe2005@gmail.com. |
| q018 | `metadata_only` | 1 | the youtube course link i saved somewhere in my calendar | yashvarpe2005@gmail.com.ics |
| q019 | `visual_recall` | 2 | that photo of me leaning on the balcony at college | WhatsApp Image 2026-06-13 at 16.58 |
| q020 | `must_refuse` | **ANSWERED** | my passport | yashvarpe2005@gmail.com.ics |
| q021 | `must_refuse` | **ANSWERED** | my college fee receipt | yashvarpe2005@gmail.com.ics |
| q022 | `must_refuse` | **ANSWERED** | the photo of me at the Taj Mahal | WhatsApp Image 2026-06-13 at 16.58 |
| q023 | `must_refuse` | **ANSWERED** | the group photo from the farewell party | WhatsApp Image 2026-06-13 at 16.58 |

## Where the failures went

Most frequent top result:

| file | times ranked first |
|---|---|
| `yashvarpe2005@gmail.com.ics` | 5 |
| `WhatsApp Image 2026-06-13 at 16.58.51.jpeg` | 4 |
| `mail.pdf` | 3 |
| `WhatsApp Image 2026-07-03 at 01.24.47 (1).jpeg` | 3 |
| `WhatsApp Image 2026-07-03 at 01.24.48.jpeg` | 2 |

`yashvarpe2005@gmail.com.ics` is the top result for 5 of 23 queries (22%).

## Stage 1 calls skipped

**15 stage 1 calls for 23 queries, cold.** The free tier allows 20 generate requests a day, so a cold run fits in one day's budget; a run without skipping needs 23 and does not.

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

- median 4303 ms, range 3070-18581 ms
- added to every search, before any retrieval happens

## Top-score distribution

Raw top similarity per query - the number refusal is decided on. Rows that
should refuse must fall below rows that should not; where they interleave,
no single threshold separates them and refusal needs a different signal.

| score | id | type |
|---|---|---|
| 0.494 | q019 | `visual_recall` |
| 0.515 | q023 | `must_refuse` |
| 0.530 | q022 | `must_refuse` |
| 0.538 | q020 | `must_refuse` |
| 0.547 | q007 | `visual_recall` |
| 0.594 | q016 | `temporal_resolution` |
| 0.599 | q017 | `metadata_only` |
| 0.606 | q001 | `visual_recall` |
| 0.619 | q010 | `disambiguation` |
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

# Analysis — fusing a selective list with a non-selective one

## The progression is the finding

| # | configuration | image vectors | Recall@1 | Recall@5 | MRR@10 | q019 |
|---|---|---|---|---|---|---|
| 1 | no visual search | 0 of 8 | 0.895 | 0.895 | 0.900 | **miss** |
| 2 | partial coverage, raw fusion | 3 of 8 | 0.895 | 0.947 | 0.921 | 2 |
| 3 | **full coverage, raw fusion** | 8 of 8 | **0.316** | 0.684 | 0.465 | 6 |
| 4 | full coverage, evidence-filtered | 8 of 8 | 0.632 | 0.947 | 0.755 | 2 |
| 5 | **full coverage, text-gated** | 8 of 8 | **0.895** | **0.947** | **0.926** | **2** |

Row 5 is the answer: **Recall@1 back to its pre-CLIP value, Recall@5 and MRR above it, and
the photo that no pre-CLIP run could find still found.** Visual search contributes exactly
where it should and nowhere else.

Per-row, every regression is repaired and nothing is traded away:

| row | no visual | evidence-filtered | text-gated |
|---|---|---|---|
| q002, q005, q008, q009, q015 | 1 | 2–4 | **1** |
| q019 | **miss** | 2 | **2** |

## The general result: RRF assumes both lists are selective

This is not a CLIP quirk and it belongs in the report as a finding about hybrid retrieval.

**Reciprocal Rank Fusion rewards a document for appearing in both lists.** That is sound
only when both lists are *selective* — when appearing in a list is itself evidence. Dense
and BM25, the pair RRF was designed for, are both selective: a document absent from the
corpus appears in neither.

**A vector index over a shared embedding space is not selective. It ranks everything.**
CLIP returns a nearest neighbour for every query, always, because cosine distance is
defined for every pair. It is not a retrieval list in the sense RRF assumes — it is a
total ordering of the corpus.

Fusing a selective list with a non-selective one **hands every dual-indexed document an
agreement bonus that a single-indexed document can never earn**, regardless of relevance.
The WhatsApp screenshots carry OCR text *and* image vectors, so they appeared in both lists
for every query and outranked text-only PDFs on queries about project reports and email.
Images topped twelve queries they had nothing to do with.

**A threshold does not fix it, and the numbers say why:**

| query | top CLIP similarity |
|---|---|
| "that photo of me leaning on the balcony at college" (correct) | **0.348** |
| "the project report about ai agents that write code" (a screenshot, wrongly) | 0.271 |
| "the list of drone topics i was supposed to learn" (a screenshot, wrongly) | 0.274 |
| "a group photo of people" (no such file exists) | 0.163 |

The genuine match is 0.348 and the noise floor is 0.22–0.28. Any threshold that admits the
first admits most of the rest. Raising 0.25 to 0.30 separates these four observations and
is **fitting a constant to four points** — the same unresolved-constant problem
`MIN_SIMILARITY_UNCALIBRATED` has had since Phase 1. This is *"absence is not low
similarity"* on the visual scale.

## The fix is structural, not tuned

**The image index contributes only documents the text index did not find.**

It follows from what CLIP is for. A photo with no text has no chunk and can never appear in
the text list at any quality — that document is the reason visual search exists. A document
already in the text list is ranked by its text, and adding a visual bonus on top is
precisely what broke ranking.

No constant. The gate is a property of the corpus — *was this document found by text?* —
rather than a number chosen to make a table look right. The evidence threshold survives as
a floor so a visually-irrelevant document cannot enter on a near-zero score, but it is no
longer doing the work.

## 3-of-8 coverage hid the bug completely

Rows 2 and 5 report the same Recall@1. The defect was **invisible** while most images
lacked vectors: with three vectors the image list was too sparse to displace anything, and
the numbers looked fine.

**The backfill did not cause this. It revealed it.** Correct coverage is what made a latent
ranking defect measurable, and a project that had shipped CLIP at partial coverage would
have carried this into every later measurement without a symptom — until enough documents
accumulated vectors to tip it, at which point the cause would have been months behind the
effect.

That is the same shape as the CLIP-unavailable branch running in every test, and as stage 1
being exercised five times: **a system is not exercised until the thing it depends on is
actually present.**

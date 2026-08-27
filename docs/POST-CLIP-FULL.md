# Stage 1 — filtered retrieval

Recorded 2026-08-27T04:02:22+00:00, commit `1229c5c`.

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
| **Recall@1** | **0.632** (12/19) |
| Recall@5 | 0.947 |
| MRR@10 | 0.755 |
| Refusal accuracy | 0.000 (0/4) |

## By query type

| type | passed | total |
|---|---|---|
| `content_semantic` | 0 | 2 |
| `disambiguation` | 4 | 4 |
| `entity_resolution` | 3 | 4 |
| `metadata_only` | 2 | 3 |
| `must_refuse` | 0 | 4 |
| `temporal_resolution` | 1 | 3 |
| `visual_recall` | 2 | 3 |

## Every query

| id | type | rank | query | top result |
|---|---|---|---|---|
| q001 | `visual_recall` | 1 | that motivation photo with the quote about working hard | 1773316539_ZnyZH84E.jpeg |
| q002 | `content_semantic` | 3 | the project report about ai agents that write code | WhatsApp Image 2026-07-03 at 01.24 |
| q003 | `disambiguation` | 1 | the synopsis about checking code for mistakes | CodeGuardAI_Synopsis.pdf |
| q004 | `disambiguation` | 1 | the project about making websites do things on their own | Relay____Synopsis.pdf |
| q005 | `content_semantic` | 3 | the list of drone topics i was supposed to learn | WhatsApp Image 2026-07-03 at 01.24 |
| q006 | `entity_resolution` | 1 | the mail yash sent to rutuja | mail.pdf |
| q007 | `visual_recall` | 1 | the screenshot of that dashboard with the forms on it | WhatsApp Image 2026-06-13 at 16.58 |
| q008 | `metadata_only` | 2 | the ai job someone forwarded to me on whatsapp | WhatsApp Image 2026-07-03 at 01.24 |
| q009 | `entity_resolution` | 3 | the job thing anu priya sent | WhatsApp Image 2026-07-03 at 01.24 |
| q010 | `disambiguation` | 1 | the tcs job where they asked to send cv on email | WhatsApp Image 2026-07-03 at 01.24 |
| q011 | `disambiguation` | 1 | the uipath job in chennai | WhatsApp Image 2026-07-03 at 01.24 |
| q012 | `entity_resolution` | 1 | the message wajeed sent about a developer role | WhatsApp Image 2026-07-03 at 01.24 |
| q013 | `entity_resolution` | 1 | the whatsapp message from aradhana | WhatsApp Image 2026-07-03 at 01.24 |
| q014 | `temporal_resolution` | 1 | when was i supposed to fill the scholarship form | yashvarpe2005@gmail.com.ics |
| q015 | `temporal_resolution` | 4 | that uber clone thing i planned to build | WhatsApp Image 2026-07-03 at 01.24 |
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
| `WhatsApp Image 2026-06-13 at 16.58.51.jpeg` | 4 |
| `WhatsApp Image 2026-07-03 at 01.24.48.jpeg` | 4 |
| `yashvarpe2005@gmail.com.ics` | 4 |
| `WhatsApp Image 2026-07-03 at 01.24.47 (1).jpeg` | 3 |
| `mail.pdf` | 2 |

`WhatsApp Image 2026-06-13 at 16.58.51.jpeg` is the top result for 4 of 23 queries (17%).

## Stage 1 calls skipped

**15 stage 1 calls for 23 queries, cold.** The free tier allows 20 generate requests a day, so a cold run fits in one day's budget; a run without skipping needs 23 and does not.

Cold is the number that matters for planning. A warm cache serves most of these rows for free, so the calls actually issued by any given run may be far fewer — which is why this says *required*, not *spent*.

Skipped means the query carried no source-type word, no sender and no date, so stage 1 had nothing to extract. Skipping cannot improve a result — it can only fail to help one. Rows skipped:

| row | query | rank | predicted harm |
|---|---|---|---|
| q002 | the project report about ai agents that write code | 3 | none predicted |
| q003 | the synopsis about checking code for mistakes | 1 | none predicted |
| q004 | the project about making websites do things on their own | 1 | none predicted |
| q005 | the list of drone topics i was supposed to learn | 3 | loses entities [drone] |
| q011 | the uipath job in chennai | 1 | loses entities [uipath, chennai] — highest risk |
| q015 | that uber clone thing i planned to build | 4 | loses entities [uber] |
| q020 | my passport | — | none predicted |
| q021 | my college fee receipt | — | none predicted |

## Stage 1 cost

An extra model call on every search. Measured across these queries:

- median 3950 ms, range 2858-29012 ms
- added to every search, before any retrieval happens

## Top-score distribution

Raw top similarity per query - the number refusal is decided on. Rows that
should refuse must fall below rows that should not; where they interleave,
no single threshold separates them and refusal needs a different signal.

| score | id | type |
|---|---|---|
| 0.494 | q015 | `temporal_resolution` |
| 0.494 | q019 | `visual_recall` |
| 0.506 | q005 | `content_semantic` |
| 0.515 | q023 | `must_refuse` |
| 0.530 | q022 | `must_refuse` |
| 0.538 | q020 | `must_refuse` |
| 0.542 | q002 | `content_semantic` |
| 0.547 | q007 | `visual_recall` |
| 0.579 | q009 | `entity_resolution` |
| 0.594 | q016 | `temporal_resolution` |
| 0.599 | q017 | `metadata_only` |
| 0.606 | q001 | `visual_recall` |
| 0.619 | q010 | `disambiguation` |
| 0.638 | q003 | `disambiguation` |
| 0.645 | q004 | `disambiguation` |
| 0.647 | q008 | `metadata_only` |
| 0.647 | q021 | `must_refuse` |
| 0.651 | q013 | `entity_resolution` |
| 0.660 | q006 | `entity_resolution` |
| 0.685 | q018 | `metadata_only` |
| 0.688 | q011 | `disambiguation` |
| 0.716 | q012 | `entity_resolution` |
| 0.764 | q014 | `temporal_resolution` |

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

# Analysis — full CLIP coverage, and what it broke

## The backfill worked; the fusion did not

| run | image vectors | Recall@1 | Recall@5 | MRR@10 |
|---|---|---|---|---|
| local qwen, pre-CLIP | 0 | 0.895 | 0.895 | 0.900 |
| after re-ingest | 3 of 8 | 0.895 | 0.947 | 0.921 |
| **after backfill, raw fusion** | **8 of 8** | **0.316** | 0.684 | 0.465 |
| **after backfill, evidence-filtered fusion** | **8 of 8** | **0.632** | **0.947** | 0.755 |

Giving every image a vector — which is *correct*, and what the backfill was for — collapsed
Recall@1 from 0.895 to 0.316. Filtering the image list to hits above
`MIN_IMAGE_SIMILARITY_UNCALIBRATED` recovered half of it. **It is still 0.263 below where
it started.**

## Why raw fusion failed

RRF rewards a document appearing in **both** lists. That is correct only if both lists are
*selective*. **CLIP is not: it returns a nearest neighbour for every query, always.**

The WhatsApp screenshots carry OCR text *and* now carry image vectors, so they appear in
both lists for every query and collect an agreement bonus that a text-only PDF can never
earn. With 3 vectors the effect was small. With 8 it dominated: images topped twelve
queries they had nothing to do with, including "the project report about ai agents" and
"the mail yash sent to rutuja".

## Why the threshold only half-fixes it

Measured against the real corpus:

| query | top CLIP similarity | what it matched |
|---|---|---|
| "that photo of me leaning on the balcony at college" | **0.348** | the correct file |
| "the project report about ai agents that write code" | **0.271** | a screenshot, wrongly |
| "the list of drone topics i was supposed to learn" | **0.274** | a screenshot, wrongly |
| "a group photo of people" (no such file) | 0.163 | nothing |

**The genuine match is 0.348 and the noise floor is 0.22–0.28.** The threshold of 0.25 sits
*inside* the noise band, so screenshots still leak through on most queries.

A threshold of 0.30 would separate these four observations. **That is fitting a constant to
four points**, and `PHASE3.md` already documents where that leads on the text side —
`MIN_SIMILARITY_UNCALIBRATED` has been an unresolved guess since Phase 1 for exactly this
reason.

**This is "absence is not low similarity" on the visual scale.** The text finding was that
a document genuinely absent can score above nine documents that are correct answers. The
visual version is narrower but the same: a screenshot CLIP has no reason to return scores
0.27 against a query about a PDF, and the correct visual answer scores 0.348. There is not
much room between them.

## Which rows are still wrong

| row | pre-CLIP | now | now tops |
|---|---|---|---|
| q002 | 1 | 3 | a WhatsApp screenshot |
| q005 | 1 | 3 | a WhatsApp screenshot |
| q008 | 1 | 2 | a WhatsApp screenshot |
| q009 | 1 | 3 | a WhatsApp screenshot |
| q015 | 1 | 4 | a WhatsApp screenshot |
| q016 | miss | 10 | mail.pdf |

Every regression is a text query outranked by an image. Note q019 stayed found and
Recall@5 held at 0.947 — **the capability works; the fusion policy is what is wrong.**

## The decision this needs, not taken here

Three options, none of them tuning:

1. **Raise the threshold.** Cheapest, and fits four data points. Likely fragile, and
   repeats the text side's unresolved-constant problem.
2. **Make visual search a fallback rather than a peer** — consult the image index only
   where the text index has weak evidence. Principled: CLIP exists to find documents the
   text index *cannot* find, because they have no text. Where text evidence is strong the
   image list can only add noise. This costs nothing at query time and needs no constant.
3. **Report the trade-off and ship text-first.** Visual search stays available and the
   report states that fusing two indexes of different selectivity is unsolved here.

**Option 2 is the one to take** on the evidence above, but it is a design change to
retrieval and it is recorded rather than applied. What is applied is the evidence filter,
which is strictly better than raw fusion and strictly worse than not fusing at all.

## What the backfill settled

`services/backfill.py` is general, not a CLIP patch: a document ingested before a
capability existed could never acquire it, and every future capability — a better OCR
engine, a different embedder, a third index — hits the same wall. The dedup path in
`uploads.py` now produces missing artifacts instead of returning early, and the CLI covers
documents nobody re-uploads.

It did its job: 5 of 5 missing vectors produced, 8 of 8 images covered. That it exposed a
fusion defect is the backfill working, not failing.

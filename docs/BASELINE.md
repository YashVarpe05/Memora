# Baseline — dense-only retrieval

Recorded 2026-08-23T18:38:27+00:00, commit `e734645`.

**This is the number query understanding has to beat.** Taken before any of it
exists, so the comparison later is a measurement rather than a reconstruction.

## What was measured

- Corpus: 11 documents, 377 chunks
- Gold set: 21 queries (19 retrieval, 2 refusal)
- Retrieval: plain dense cosine over `gemini-embedding-001` at 768 dims. No query understanding, no BM25, no reranking.
- Ingest took 247s, almost all of it free-tier rate limiting.

## Headline

| metric | value |
|---|---|
| **Recall@1** | **0.842** (16/19) |
| Recall@5 | 0.947 |
| MRR@10 | 0.895 |
| Refusal accuracy | 0.000 (0/2) |

## By query type

| type | passed | total |
|---|---|---|
| `content_semantic` | 2 | 2 |
| `disambiguation` | 4 | 4 |
| `entity_resolution` | 3 | 4 |
| `metadata_only` | 3 | 3 |
| `must_refuse` | 0 | 2 |
| `temporal_resolution` | 3 | 3 |
| `visual_recall` | 1 | 3 |

## Every query

| id | type | rank | query | top result |
|---|---|---|---|---|
| q001 | `visual_recall` | 1 | that motivation photo with the quote about working hard | 1773316539_ZnyZH84E.jpeg |
| q002 | `content_semantic` | 1 | the project report about ai agents that write code | AgentOS_Synopsis.pdf |
| q003 | `disambiguation` | 1 | the synopsis about checking code for mistakes | CodeGuardAI_Synopsis.pdf |
| q004 | `disambiguation` | 1 | the project about making websites do things on their own | Relay____Synopsis.pdf |
| q005 | `content_semantic` | 1 | the list of drone topics i was supposed to learn | mail.pdf |
| q006 | `entity_resolution` | 2 | the mail yash sent to rutuja | yashvarpe2005@gmail.com.ics |
| q007 | `visual_recall` | 2 | the screenshot of that dashboard with the forms on it | yashvarpe2005@gmail.com.ics |
| q008 | `metadata_only` | 1 | the ai job someone forwarded to me on whatsapp | WhatsApp Image 2026-07-03 at 01.24 |
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
| q019 | `visual_recall` | **miss** | that photo of me leaning on the balcony at college | yashvarpe2005@gmail.com.ics |
| q020 | `must_refuse` | **ANSWERED** | my passport | yashvarpe2005@gmail.com.ics |
| q021 | `must_refuse` | **ANSWERED** | my college fee receipt | yashvarpe2005@gmail.com.ics |

## Where the failures went

Every failed query has the same file at rank 1.

| file | times ranked first |
|---|---|
| `yashvarpe2005@gmail.com.ics` | 8 of 21 |

The calendar is 353 of 377 chunks — **94% of the corpus**. A document that large contains
something marginally similar to almost any query, so under dense-only ranking it becomes
an attractor: it wins q006 ("the mail yash sent to rutuja"), q007 ("the screenshot of that
dashboard"), and both refusal rows.

**This is the single clearest argument in this table for query understanding.** Stage 1
constrains by source type and date *before* searching, and an attractor stops competing
for queries it has no business answering. "The mail yash sent" filters to `source_type:
email`; "the screenshot" filters to `source_type: image`. Neither needs better embeddings.

Note this was appended by hand from the recorded run's own data. The renderer now computes
it, but the free-tier daily quota (1000 embed requests; one full ingest is ~400) was
exhausted before a regenerating run could complete.

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
- **Free-tier quota bounds how often this can be re-measured.** 1000 embed requests per day, and one full corpus ingest is roughly 400 — about two runs a day.
- **Tesseract is the only working OCR engine.** PaddleOCR installs and cannot run on this hardware, in the container as well as on Windows.


# Stage 1 — filtered retrieval

Recorded 2026-08-25T18:15:04+00:00, commit `466abfa`.

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
| q020 | `must_refuse` | **ANSWERED** | my passport | WhatsApp Image 2026-06-13 at 16.58 |
| q021 | `must_refuse` | **ANSWERED** | my college fee receipt | Relay____Synopsis.pdf |

## Where the failures went

Most frequent top result:

| file | times ranked first |
|---|---|
| `yashvarpe2005@gmail.com.ics` | 4 |
| `Relay____Synopsis.pdf` | 3 |
| `mail.pdf` | 3 |
| `WhatsApp Image 2026-06-13 at 16.58.51.jpeg` | 3 |
| `WhatsApp Image 2026-07-03 at 01.24.47 (1).jpeg` | 2 |

`yashvarpe2005@gmail.com.ics` is the top result for 4 of 21 queries (19%).

## Stage 1 cost

An extra model call on every search. Measured across these queries:

- median 0 ms, range 0-2310 ms
- added to every search, before any retrieval happens

## Top-score distribution

Raw top similarity per query - the number refusal is decided on. Rows that
should refuse must fall below rows that should not; where they interleave,
no single threshold separates them and refusal needs a different signal.

| score | id | type |
|---|---|---|
| 0.494 | q019 | `visual_recall` |
| 0.497 | q020 | `must_refuse` |
| 0.528 | q010 | `disambiguation` |
| 0.546 | q021 | `must_refuse` |
| 0.547 | q007 | `visual_recall` |
| 0.562 | q016 | `temporal_resolution` |
| 0.567 | q012 | `entity_resolution` |
| 0.599 | q017 | `metadata_only` |
| 0.606 | q001 | `visual_recall` |
| 0.622 | q009 | `entity_resolution` |
| 0.638 | q003 | `disambiguation` |
| 0.645 | q004 | `disambiguation` |
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

# Analysis — the falsifier for the skip

Everything above is generated and regenerable. This is the test `PHASE3C.md` promised:
run stage 1 on **every** row, including the eight the heuristic skips, and see what the
skipped rows would have got.

## Result: not one row moved

| metric | skip arm (`PHASE3C.md`) | no-skip arm | change |
|---|---|---|---|
| Recall@1 | 0.842 | 0.842 | — |
| Recall@5 | 0.947 | 0.947 | — |
| MRR@10 | 0.870 | 0.870 | — |

**All 21 rows are identical, rank for rank.** Not "the headline is unchanged" — every
individual row, including the three the harm table named.

| prediction | outcome |
|---|---|
| q005, q011, q015 all stay rank 1 | **HELD.** All three, in both arms. |
| Recall@1 stays 0.842 | **HELD.** |
| q005 or q015 moving would mean the arms differ by more than the heuristic | **did not happen** |

## The flag really ran, which had to be checked

An identical result is also what a broken flag produces, so the arms were verified to
differ before the numbers were read:

- the no-skip report has **no "Stage 1 calls skipped" section** — zero rows skipped
- stage 1 latency ranges **0–2310 ms** here against **0–0 ms** in the skip arm, so real
  calls were made rather than served from cache
- **all 21 gold rows are now cached for `gemini-2.5-flash`**, up from 16. The five cold
  ones were extracted during this run, which is only possible if stage 1 ran on them

## What the skipped rows actually extract

Asked directly, the eight skipped rows split evenly:

| row | extraction when forced | rank |
|---|---|---|
| q002 | `source_types: [pdf]` | 1 both ways |
| q011 | `entities: [uipath, chennai]` | 1 both ways |
| q020 | `source_types: [pdf, image]` | answered both ways |
| q021 | `source_types: [pdf, image, email]` | answered both ways |
| q003, q004, q005, q015 | **nothing usable** | 1 both ways |

**Four of eight produce no filter even when asked**, so the call is pure waste for them.
The other four produce a filter that changes nothing — including q011, whose
`[uipath, chennai]` was the single highest-confidence harm in the phase-3c prediction table.

## What this settles, and what it does not

**Settles:** the skip costs nothing measurable on this gold set. The `PHASE3C.md` decision
to keep it against the pre-agreed threshold is now supported by a direct test rather than
by an argument about attribution.

**Does not settle:** whether the skip is safe in general. Twenty-one queries over eleven
documents is a small corpus, and q011 shows a real filter can be discarded with no
consequence *here* only because the answer was already rank 1 on dense similarity. On a
corpus with more near-duplicate job postings, the same discard could cost the row. The
honest claim is **"no measured harm", not "no harm"**.

**A note on the budget.** This run took the day's successful generate calls to roughly 22,
past the 20/day ceiling recorded in `PHASE3.md`, without a 429. Either that limit is wrong
or it has changed. It is the number the whole throughput argument rests on, so it needs
re-measuring rather than restating — flagged here, not fixed here.

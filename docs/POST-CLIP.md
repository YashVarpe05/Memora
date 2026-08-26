# Stage 1 — filtered retrieval

Recorded 2026-08-26T09:52:40+00:00, commit `88a3510`.

**Query understanding is ON.** Compare against `BASELINE.md`, which is the
same corpus and gold set with stage 1 disabled.

## What was measured

- Corpus: 14 documents, 377 chunks
- Gold set: 23 queries (19 retrieval, 4 refusal)
- Retrieval: dense cosine over `gemini-embedding-001` at 768 dims, with stage 1 filters applied as boosts.
- Ingest took 9s, almost all of it free-tier rate limiting.

## Headline

| metric | value |
|---|---|
| **Recall@1** | **0.895** (17/19) |
| Recall@5 | 0.947 |
| MRR@10 | 0.921 |
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
| q016 | `temporal_resolution` | **miss** | what i had planned to learn last year | mail.pdf |
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

- median 4385 ms, range 2880-17007 ms
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

# Analysis — the corpus re-ingested with CLIP

## q019 is found for the first time

| | before CLIP | after |
|---|---|---|
| documents indexed | 11 | **14** |
| **q019** "that photo of me leaning on the balcony at college" | **miss** | **rank 2** |
| q016 "what i had planned to learn last year" | 10 | miss |
| Recall@1 | 0.895 | 0.895 |
| Recall@5 | 0.895 | **0.947** |
| MRR@10 | 0.900 | **0.921** |

**Three files that were rejected at ingest are now indexed**, and q019 — a guaranteed miss
in every run this project has ever recorded, because its file has no extractable text and
was refused at upload — is now found at rank 2.

That is the capability CLIP was added for, demonstrated on the row it was predicted to fix.
It is rank 2 rather than rank 1, so the prediction "q019 flips to rank 1" is **broken as
stated and held in substance**: the file went from unreachable to second.

**q016 got worse, from rank 10 to a miss.** That is not CLIP: qwen fails to resolve "last
year" into a date and emits four spurious source types instead, and three more documents in
the corpus give that wrong filter more to promote. The local extractor's known weakness,
amplified by a larger corpus.

## Only 3 of 14 documents have a CLIP vector — a defect

```
image_embeddings: 3
  DSC02946.JPG
  image-removebg-preview (1).png
  Still-5-Copyright_-...webp
```

The WhatsApp screenshots — the majority of the image corpus — have **no image vector at
all**. The cause is deduplication: `find_by_hash` matches the content hash of a document
ingested before CLIP existed and returns early, so the embedding step never runs.

**A document ingested before a capability existed can never acquire it.** That is a real
defect in the ingest path, not a property of CLIP, and it means this measurement understates
visual search by a wide margin — it ran on 3 documents out of 14.

Reported before fixing, per the working rule. The minimal correction is for the dedup path
to add a missing image embedding rather than returning early.

## The absence controls did not refuse — and it is not CLIP's fault

q022 and q023 were added as visual absence controls, and both were **ANSWERED**. Before
attributing that to visual search, the scores say otherwise:

| row | raw top score | index |
|---|---|---|
| q023 | 0.515 | **text** |
| q022 | 0.530 | **text** |
| q020 | 0.538 | text |
| q021 | 0.647 | text |

All four are answered on **text** similarity against the calendar, comfortably above
`MIN_SIMILARITY_UNCALIBRATED = 0.35`. This is the same pre-existing gap `PHASE3.md`
documented — refusal is not implemented, and "absence is not low similarity". The new
controls fail for the same reason the old ones do.

**So visual search did not make refusal worse.** It also has not yet been tested against
refusal, because the text index answers these queries before the visual one is consulted.
The controls remain valid and remain unpassed.

## What this measurement is and is not

- **It is** the first run where a text-free document is retrievable, and the first where
  the corpus is complete at 14 documents.
- **It is not** comparable to `BASELINE.md` (0.842) or `PHASE3C.md`: the corpus is larger
  and a second retrieval index is active. Those numbers describe an 11-document,
  text-only system.
- **It undersells CLIP**, because 11 of 14 documents were never given a vector.

# Stage 1 — filtered retrieval

Recorded 2026-08-26T09:17:33+00:00, commit `5b966cf`.

**Query understanding is ON.** Compare against `BASELINE.md`, which is the
same corpus and gold set with stage 1 disabled.

## What was measured

- Corpus: 11 documents, 377 chunks
- Gold set: 23 queries (19 retrieval, 4 refusal)
- Retrieval: dense cosine over `gemini-embedding-001` at 768 dims, with stage 1 filters applied as boosts.
- Evaluated against an already-indexed corpus, verified by content hash.

## Headline

| metric | value |
|---|---|
| **Recall@1** | **0.895** (17/19) |
| Recall@5 | 0.895 |
| MRR@10 | 0.902 |
| Refusal accuracy | 0.000 (0/4) |

## By query type

| type | passed | total |
|---|---|---|
| `content_semantic` | 2 | 2 |
| `disambiguation` | 4 | 4 |
| `entity_resolution` | 3 | 4 |
| `metadata_only` | 3 | 3 |
| `must_refuse` | 0 | 4 |
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
| q006 | `entity_resolution` | 7 | the mail yash sent to rutuja | WhatsApp Image 2026-07-03 at 01.24 |
| q007 | `visual_recall` | 1 | the screenshot of that dashboard with the forms on it | WhatsApp Image 2026-06-13 at 16.58 |
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
| q019 | `visual_recall` | **miss** | that photo of me leaning on the balcony at college | WhatsApp Image 2026-06-13 at 16.58 |
| q020 | `must_refuse` | **ANSWERED** | my passport | yashvarpe2005@gmail.com.ics |
| q021 | `must_refuse` | **ANSWERED** | my college fee receipt | yashvarpe2005@gmail.com.ics |
| q022 | `must_refuse` | **ANSWERED** | the photo of me at the Taj Mahal | WhatsApp Image 2026-06-13 at 16.58 |
| q023 | `must_refuse` | **ANSWERED** | the group photo from the farewell party | WhatsApp Image 2026-06-13 at 16.58 |

## Where the failures went

Most frequent top result:

| file | times ranked first |
|---|---|
| `yashvarpe2005@gmail.com.ics` | 6 |
| `WhatsApp Image 2026-06-13 at 16.58.51.jpeg` | 4 |
| `WhatsApp Image 2026-07-03 at 01.24.48.jpeg` | 3 |
| `WhatsApp Image 2026-07-03 at 01.24.47 (1).jpeg` | 3 |
| `1773316539_ZnyZH84E.jpeg` | 1 |

`yashvarpe2005@gmail.com.ics` is the top result for 6 of 23 queries (26%).

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

- median 4441 ms, range 3481-27596 ms
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
| 0.577 | q006 | `entity_resolution` |
| 0.599 | q017 | `metadata_only` |
| 0.603 | q016 | `temporal_resolution` |
| 0.606 | q001 | `visual_recall` |
| 0.619 | q010 | `disambiguation` |
| 0.622 | q009 | `entity_resolution` |
| 0.638 | q003 | `disambiguation` |
| 0.645 | q004 | `disambiguation` |
| 0.647 | q021 | `must_refuse` |
| 0.651 | q013 | `entity_resolution` |
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

# Analysis — Llama 3.2 3B, and the two local models compared

## Same score, different failures

| arm | Recall@1 | Recall@5 | MRR@10 |
|---|---|---|---|
| dense-only | 0.842 | 0.947 | 0.895 |
| **qwen2.5:3b-instruct** | **0.895** | 0.895 | 0.900 |
| **llama3.2:3b** | **0.895** | 0.895 | 0.902 |
| hosted, old prompt | 0.842 | 0.947 | 0.870 |
| flash-lite (rejected) | 0.789 | | |

Both local models clear the 0.842 bar, and both land on **exactly the same number**. That
looks like a tie, and reading it as one would miss the actual result.

**They differ on two rows, and they are opposite rows:**

| row | qwen | llama | what it needs |
|---|---|---|---|
| **q006** "the mail yash sent to rutuja" | **1** | **7** | the counter-intuitive rule that a scanned email is `pdf`, not `email` |
| **q016** "what i had planned to learn last year" | **10** | **1** | relative date arithmetic against the supplied current date |

Every other row is identical across both. **Two 3B models with the same prompt, the same
schema, the same seed and the same score fail on disjoint tasks.** Qwen can do the
prompt-following rule and not the arithmetic; Llama can do the arithmetic and not the rule.

That is a more useful finding than either number:

- **An aggregate score hid it completely.** 0.895 versus 0.895 says "equivalent". The rows
  say the two models have different competencies, and a report that stopped at Recall@1
  would have concluded they were interchangeable.
- **It falsifies the phase's risk table in both directions at once.** q006 was predicted
  *highest* risk — correct for Llama, wrong for Qwen. q016 was predicted *moderate* — wrong
  for Llama, correct for Qwen. The prediction was about "small models" as a category, and
  the category does not behave uniformly.
- **The union is 19/19 on these two rows.** Neither model alone reaches hosted's predicted
  0.947, but no single row defeats both. That is a real observation and **not** a
  recommendation: routing between two models is a second classifier, and this project has
  measured what a wrong classifier costs. It is recorded as an observation for the report,
  not a design.

## The control

All 8 rows the signal heuristic skips are identical across both local arms and
`PHASE3C.md`. Both arms isolate the extractor.

## What this does not settle

- **Hosted under the same prompt.** `PHASE3D.md` is still blocked on quota and remains the
  only clean model-to-model comparison.
- **Whether the split generalises.** Two rows, one corpus, one seed. The direction is
  interesting; the magnitude is not evidence of anything.
- **Llama's first run measured nothing.** All 15 calls failed with "model not found"
  because the download had been cut off at 84%, and the harness refused to write it. Same
  guard as the quota outages, catching a different cause — and worth noting that a missing
  model and an exhausted quota are indistinguishable at the call site, which is exactly why
  the gate is on the failure *rate* rather than the reason.

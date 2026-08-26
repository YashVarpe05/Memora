# Stage 1 — filtered retrieval

Recorded 2026-08-26T08:56:31+00:00, commit `5b966cf`.

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
| MRR@10 | 0.900 |
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
| q019 | `visual_recall` | **miss** | that photo of me leaning on the balcony at college | WhatsApp Image 2026-06-13 at 16.58 |
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

- median 5057 ms, range 3608-6717 ms
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

# Analysis — local stage 1 on Qwen 2.5 3B

Everything above is generated. This is written, and records what the run settles.

## Result: 0.895, above the bar

| arm | model | Recall@1 | Recall@5 | MRR@10 |
|---|---|---|---|---|
| dense-only | none | 0.842 | 0.947 | 0.895 |
| **local** | **qwen2.5:3b-instruct** | **0.895** | 0.895 | 0.900 |
| hosted, old prompt | gemini-2.5-flash | 0.842 | 0.947 | 0.870 |
| hosted, new prompt | gemini-2.5-flash | *unmeasured — quota* | | |
| rejected | gemini-flash-lite | 0.789 | | |

**The bar was 0.842, and a 3B model on a laptop CPU cleared it.** That is the result the
phase turned on: local stage 1 is worth having at all, so every ceiling it removes — the
20/day cap, the deprecation risk in `MODEL-RISK.md`, the query leaving the device — can be
removed without paying for it in accuracy.

## The confound, untangled without spending quota

**The local arm runs the phase-3d prompt; `PHASE3C.md`'s hosted arm ran the one before
it.** So "0.895 local vs 0.842 hosted" compares two things at once, and reading it as a
model comparison would be wrong.

It was untangled by comparing **extractions** rather than ranks — free, because the hosted
extractions under the new prompt are already cached:

| row | hosted, new prompt | qwen | verdict |
|---|---|---|---|
| q010 | `[email, pdf, image]` | `[pdf, email, image]` | **same intent** — both gained `image` |
| q012 | `[chat, email, image, pdf]`, sender `wajeed` | `[image, email]`, **no sender** | both gained `image`; qwen misses the sender |
| q016 | `[]`, `after=2025-01-01` | `[pdf, image, email, chat]`, **no date** | **qwen fails outright** |

So the gains on q010 and q012 belong to **the prompt fix, not the model** — both extractors
produce the `image` filter once the screenshot sentence exists. That is also the first
independent evidence the phase-3d sentence works, obtained without a hosted call.

**The arithmetic reconciles exactly.** Hosted old prompt: 16/19. The prompt fix recovers
q010 and q012 to 18/19 = 0.947, which is precisely the standing phase-3d prediction. Qwen
gets those two and then loses q016: **17/19 = 0.895**.

**Local stage 1 is hosted stage 1 minus one row, and that row is the temporal one.**

## Where the small model actually fails

Both weaknesses are visible in the extractions rather than inferred from ranks:

1. **Relative dates.** q016 "what i had planned to learn last year" needs
   `after=2025-01-01`. Hosted resolves it against the supplied current date and returns no
   source-type filter. Qwen returns **no date at all and four source types** — worse than
   useless, because that is a *wrong* filter and `PHASE3.md` measured what those cost. The
   row fell from rank 1 to rank 10, which is also why Recall@5 dropped to 0.895 while every
   other arm holds 0.947.
2. **`sender` extraction.** Missed on q012, and on q013 in spot testing where the query
   literally reads "from aradhana". The field is optional in the JSON schema and small
   models skip optional fields. **Not tuned before measuring, deliberately** — the
   predictions were written against this schema, and making `sender` required after seeing
   the result would be fitting the method to the answer. It is the first thing to try next.

## Predictions, marked

Recorded in `prompts/local-stage1.md` before Ollama was installed.

| prediction | outcome |
|---|---|
| Valid JSON on ≥22 of 23 | **HELD.** 23 of 23, zero extraction failures. |
| Recall@1 between 0.789 and 0.947 | **HELD.** 0.895. |
| **Recall@1 ≥ 0.842 — the bar, called 50/50** | **HELD.** |
| CPU latency 5–20 s | **HELD.** ~7.5 s warm; 89 s on the first call, including model load. |
| The 8 skipped rows identical across arms | **HELD.** All 8 match `PHASE3C.md` exactly. |
| q006 highest risk — the scanned-email rule | **BROKEN.** q006 holds rank 1; qwen produces `pdf` correctly. A 3B model learned the counter-intuitive rule from the prompt. |
| q010, q012 high risk | **BROKEN, and inverted.** Both *improved* to rank 1 — from the prompt, not the model. |
| q016 moderate risk | **HELD.** The only row lost, and lost badly. |
| q013, q009 low risk | **HELD for rank, wrong mechanism.** Both rank 1, but q013 holds on similarity despite qwen missing the sender entirely. |

**The risk table got the direction wrong on three of five rows.** The rows predicted
hardest were fine; the loss came from the one arithmetic-shaped task. The intuition
"counter-intuitive prompt rules are hard for small models" was wrong. "Date arithmetic is
hard for small models" was right.

## The control

The 8 rows the signal heuristic skips never reach stage 1, so they must be identical across
arms. **All 8 match `PHASE3C.md` rank for rank**, including both refusal rows. The arm
isolates the extractor and nothing else.

## Latency

| | per query |
|---|---|
| first call, cold | 89 s — model load |
| warm | **~7.5 s** |
| hosted | 2–3 s |

Three times slower than hosted, and **the search UI already handles it**: dense results
paint in ~50 ms and re-rank when stage 1 lands. A slow local extractor degrades into the
arm that already works — the same property that makes a *failed* extractor safe.

The cold 89 s is a real operational fact: a container restart makes the first search of the
day very slow. Keeping the model resident is a configuration question, not a research one.

## What this does not settle

- **Hosted under the same prompt is still unmeasured.** `PHASE3D.md` is blocked on quota
  and is the only clean model-to-model comparison. The reconciliation above predicts 0.947
  for it, which makes it a testable claim rather than a hope.
- **Llama 3.2 3B is unmeasured.** Its first run failed on all 15 calls because the model was
  not actually present — the download had been cut off at 84% — and the harness refused to
  write the run. The same guard, catching a different failure: a missing model rather than
  an exhausted quota.
- **One corpus, 23 queries, one seed.** Deterministic (`temperature=0`, fixed seed), so it
  reproduces — but it is not a distribution.

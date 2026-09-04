# Results

Every figure in this chapter comes from a committed measurement file. The source is named
beside each table. Where a number has no file behind it, that is said explicitly rather
than smoothed over.

**Corpus and gold set.** Measurements up to and including §3 use 11 documents and 377
chunks with a 21-row gold set. From §4 onward the corpus is 14 documents — three files that
had been rejected at ingest for containing no extractable text became ingestable once
visual search existed — and the gold set is 23 rows, with two visual absence controls
added. **Numbers either side of that boundary are not directly comparable**, and the
boundary is marked where it occurs.

**Metrics.** Recall@1 is the fraction of answerable rows whose expected file ranks first —
the product's definition of success, since the answer is the file. Recall@5 and MRR@10 are
secondary. Refusal accuracy is measured over the `must_refuse` rows, which have no expected
file and are therefore excluded from recall.

---

## 1. Dense-only baseline

*Source: `BASELINE.md`*

| metric | value |
|---|---|
| **Recall@1** | **0.842** (16/19) |
| Recall@5 | 0.947 |
| MRR@10 | 0.895 |
| Refusal accuracy | 0.000 (0/2) |

Recorded before query understanding existed, so the comparison that follows is a
measurement rather than a reconstruction. Three rows fail: two are recovered by later
phases, one (q019) has no extractable text and is unreachable until §4.

## 2. Adding stage 1 — query understanding

*Source: `PHASE3.md`*

| metric | dense only | + stage 1 (hosted) | change |
|---|---|---|---|
| **Recall@1** | 0.842 (16/19) | **0.947 (18/19)** | **+0.105** |
| Recall@5 | 0.947 | 0.947 | — |
| MRR@10 | 0.895 | 0.947 | +0.052 |
| Refusal accuracy | 0.000 (0/2) | 0.000 (0/2) | — |

Two rows moved from rank 2 to rank 1. **This is the project's central result** and the
argument for two-stage retrieval: most personal-document queries are metadata queries in
semantic clothing, and filtering before searching recovers rows that pure similarity ranks
second.

> **Provenance caveat, stated because it matters.** The 0.947 was transcribed by hand from
> console output; a later run overwrote the file before archiving existed. Every subsequent
> run in this chapter is archived. This is the only figure here without a machine-written
> file behind it.

### A negative result that shaped everything after it

*Source: `PHASE3.md`*

Substituting `gemini-flash-lite-latest` for the pinned model — done to work around a quota
limit — produced **Recall@1 0.789**, which is *below the 0.842 achieved by using no
extractor at all*.

**A wrong filter is worse than no filter.** Soft filters bound the damage without removing
it: a mismatching document is demoted, so a wrong extraction actively pushes the correct
answer down. This number set the acceptance bar for every later extractor: **0.842, not
0.947.**

## 3. Two ablations on stage 1

*Sources: `PHASE3C.md`, `PHASE3C-NOSKIP.md`*

Stage 1 costs one model call per search. A local heuristic skips it when the query carries
no source type, sender or date — 8 of 21 rows.

| arm | Recall@1 | Recall@5 | MRR@10 |
|---|---|---|---|
| skip heuristic on | 0.842 (16/19) | 0.947 | 0.870 |
| **stage 1 forced on every row** | **0.842 (16/19)** | 0.947 | 0.870 |

**All 21 rows identical, rank for rank.** Not merely an unchanged headline — no individual
row moved, including the three a pre-registered harm table had named. Forced extraction
showed why: four of the eight skipped rows produce **no usable filter even when asked**, and
the other four produce filters that change no ranking.

> Both runs report 0.842 rather than §2's 0.947 because they use a later prompt and a
> different measurement session. §5 shows the same two rows recovering under a corrected
> prompt, which reconciles the difference.

## 4. Hosted versus local stage 1

*Sources: `PHASE3-LOCAL.md`, `LOCAL-QWEN.md`, `LOCAL-LLAMA.md`*

| extractor | Recall@1 | Recall@5 | MRR@10 | quota | reproducible |
|---|---|---|---|---|---|
| none (dense only) | 0.842 | 0.947 | 0.895 | — | yes |
| `gemini-flash-lite` | 0.789 | — | — | metered | no |
| **`qwen2.5:3b` local** | **0.895** (17/19) | 0.895 | 0.900 | **none** | **yes** |
| **`llama3.2:3b` local** | **0.895** (17/19) | 0.895 | 0.902 | **none** | **yes** |
| `gemini-2.5-flash` hosted | 0.947 | 0.947 | 0.947 | 20/day | **no** |

Both 3B models running on a laptop CPU clear the 0.842 bar, with **zero extraction failures
across 23 queries** — constrained JSON decoding removes the malformed-output failure class
entirely.

### The finding is not the score

**The two models score identically and fail on opposite rows.**

| row | what it needs | qwen2.5:3b | llama3.2:3b |
|---|---|---|---|
| q006 "the mail yash sent to rutuja" | a counter-intuitive prompt rule (a scanned email is a PDF) | **rank 1** | rank 7 |
| q016 "what i had planned to learn last year" | relative date arithmetic | rank 10 | **rank 1** |
| all other rows | — | identical | identical |

An aggregate metric reports these two systems as equivalent. They are not: one follows a
counter-intuitive instruction and cannot do arithmetic, the other does the arithmetic and
ignores the instruction. **Substituting one for the other changes which queries work while
leaving every summary statistic unchanged.**

The union covers both rows. That is recorded as an observation and **not** as a design:
routing between extractors is a second classifier, and the 0.789 result above measures what
a wrong classifier costs.

### Latency

*Source: `PHASE3-LOCAL.md`*

| | per query |
|---|---|
| local, warm | ~7.5 s |
| local, first call after container start | 89 s (model load) |
| hosted | 2–3 s |

Three times slower. The interface absorbs it: dense-only results paint in ~50 ms and
re-rank when stage 1 returns, so a slow extractor degrades into the arm that already works.

## 5. Visual search — four fusion configurations

*Sources: `POST-CLIP.md`, `POST-CLIP-FULL.md`, `LOCAL-TEXTGATED.md`*

**Corpus boundary: 14 documents, 23 gold rows from here on.**

CLIP ViT-B/32 embeds images and text into one space, so a photograph with no text becomes
findable. The question was how to combine two indexes.

| # | configuration | image vectors | Recall@1 | Recall@5 | MRR@10 | q019 |
|---|---|---|---|---|---|---|
| 1 | no visual search | 0 of 8 | 0.895 | 0.895 | 0.900 | **miss** |
| 2 | partial coverage, raw RRF | 3 of 8 | 0.895 | 0.947 | 0.921 | 2 |
| 3 | **full coverage, raw RRF** | 8 of 8 | **0.632** (12/19) | 0.947 | 0.755 | 6 |
| 4 | **full coverage, text-gated** | 8 of 8 | **0.895** (17/19) | 0.947 | **0.926** | **2** |

> Row 3 as tabulated is the **evidence-filtered** intermediate. Unfiltered RRF at full
> coverage measured **Recall@1 0.316**, recorded in the analysis section of
> `POST-CLIP-FULL.md`; that run was overwritten by the filtered one before archiving, so
> 0.316 traces to a committed note rather than to a generated report.

**q019 — "that photo of me leaning on the balcony at college" — was a miss in every run
before §5.** Its file has no extractable text and was rejected at ingest. It is now
retrievable by description.

### Why full coverage broke ranking

**RRF rewards a document for appearing in both lists, which is sound only when both lists
are selective.** Dense and BM25, the pair RRF was designed for, both are: a document absent
from the corpus appears in neither.

**A vector index over a shared embedding space is not selective — it ranks everything.**
Cosine distance is defined for every pair, so CLIP returns a nearest neighbour for every
query. It is not a retrieval list in the sense RRF assumes; it is a total ordering of the
corpus.

Fusing a selective list with a non-selective one hands every dual-indexed document an
agreement bonus a single-indexed document can never earn. The WhatsApp screenshots carry
OCR text *and* image vectors, so they appeared in both lists for every query and topped
twelve queries they had nothing to do with.

**A threshold cannot separate them.** Measured CLIP similarities:

| query | top similarity | correct? |
|---|---|---|
| "that photo of me leaning on the balcony at college" | 0.348 | yes |
| "the project report about ai agents that write code" | 0.271 | no — a screenshot |
| "the list of drone topics i was supposed to learn" | 0.274 | no — a screenshot |
| "a group photo of people" (no such file) | 0.163 | correctly nothing |

The genuine match is 0.348 and the noise floor is 0.22–0.28. Any threshold admitting the
first admits most of the rest. **This is "absence is not low similarity" on the visual
scale.**

**The fix is structural and uses no constant: the image index contributes only documents
the text index did not find.** It follows from what visual search is for — a photo with no
text can never appear in the text list at any quality, and that document is the reason the
second index exists. A document already found by text is ranked by its text.

## 6. Refusal

*Source: `PHASE3B.md`*

| metric | before | after |
|---|---|---|
| **Refusal accuracy** | 0.000 (0/4) | **0.500 (2/4)** |
| Recall@1 | 0.895 | **0.895** |
| Recall@5 | 0.947 | **1.000** |
| MRR@10 | 0.926 | **0.932** |

**No threshold can implement refusal**, and the score distribution shows why: q021 ("my
college fee receipt", absent) scores 0.647 — above nine documents that are the correct
answer to their own query — because the calendar genuinely contains events about college and
fees. Catching q021 by score means refusing eight correct answers.

**Document-type agreement tests what the user asked for.** Stage 1 extracts
`document_type`; the corpus is queried for the types it holds; a named type that is absent
refuses regardless of similarity.

| row | outcome |
|---|---|
| q020 "my passport" | **refused** |
| q021 "my college fee receipt" | **refused** |
| q022 "the photo of me at the Taj Mahal" | answered |
| q023 "the group photo from the farewell party" | answered |

**Zero false refusals**, against a pre-registered prediction of 1–2. Recall@5 reached 1.000
for the first time.

**0.500 is the mechanism's ceiling on this gold set, not a partial implementation.** q022
and q023 name no document type — "photo" is deliberately excluded from the vocabulary,
because treating it as a type would refuse every genuine photo query. They are visual
absence controls and remain unsolved: CLIP returns a nearest neighbour for every query, so
the visual index cannot report absence any more than the text index can.

---

## 7. Fusing heterogeneous retrieval — one root cause, two failures

*Sources: `data/eval-runs/20260904T105531-stage1.md`, `…112353…`, `…112853…`,
`…113316…`, `…113956…`; plan and pre-registered predictions in
`prompts/chunk-dominance.md`*

Reciprocal Rank Fusion is used twice in this system: dense with BM25, and text with CLIP.
It failed both times on this corpus, in ways that look unrelated and are not. **They are
one root cause with two manifestations**, and naming it that way is the finding.

RRF consumes ranks rather than scores, which is why it is the right tool for combining
retrievers whose scores are on different scales. But it carries two preconditions that its
scale-independence does nothing to protect:

1. **The lists are comparably selective.** A document absent from what a list is about
   should be absent from that list.
2. **The lists are independently informative.** Agreement between them should be evidence,
   which requires that agreement was possible and not guaranteed.

Neither failure below is a defect in RRF. Both are its preconditions going unchecked
against heterogeneous retrieval.

### 7.1 A selective list fused with a non-selective one

Measured 2026-08-26 and reported in §5: fusing the raw CLIP list dropped Recall@1 from
0.895 to 0.316. Dense and BM25 are both selective — a document unrelated to the query
appears in neither. **A vector index over a shared embedding space is not: it ranks
everything.** So documents carrying both OCR text and image vectors appeared in both lists
for every query and collected an agreement bonus a text-only PDF could never earn.
Precondition 1 violated, and the agreement term became a property of the document's
modality rather than of the query.

The fix was to gate on text evidence: consult the image index only where text is weak.
That restored 0.895 — and created the second failure.

### 7.2 Disjoint lists, where the agreement term can never fire

Text gating drops any image hit whose document the text index already found. **That makes
the two lists disjoint by construction**, so no document can appear in both and RRF's
agreement term is unreachable. Precondition 2 violated — this time by the fix for the
first violation.

With the agreement term dead, `score = 1/(k + rank)` from exactly one list, and fusion
degenerates into interleaving by rank position. A document at image rank 1 and a document
at text rank 1 then score **1/61 each: an exact tie.** Python's `sorted` is stable, the
text side is merged first, and so the text document keeps the position.

The consequence is structural rather than occasional:

> A document found only by the image index beats text rank 2 (1/61 > 1/62) and can never
> beat text rank 1. **Purely visual retrieval was capped at rank 2** — by insertion order,
> not by any score.

Both Recall@1 misses sat at rank 2 with score 0.0164, and no threshold explained them
because no similarity was involved. `0.0164` is not a similarity; it is `1/(60+1)`.

**The fix was to make the tie-break a decision.** Ties now resolve on document-type
agreement, then on own-modality strength — text against `MIN_SIMILARITY_UNCALIBRATED`,
images by the gate they already passed — so neither side is ever compared against the
other's scale, and no constant was introduced. The RRF score stays the primary key, so a
document that was not tied cannot move.

| variant | Recall@1 | Recall@5 | MRR@10 | refusal |
|---|---|---|---|---|
| max-per-chunk, before | 0.900 | 1.000 | 0.950 | 0.500 |
| **tie-break** | **0.950** | 1.000 | 0.975 | 0.500 |
| tie-break + chunk damping α=0.05 | 0.850 | 0.950 | 0.906 | 0.500 |
| tie-break, with q025 added | 0.905 | 1.000 | 0.952 | 0.500 |

### 7.3 The rank-1 cap on purely visual retrieval is NOT fixed — q025 measures it

**q024 passing does not demonstrate visual retrieval reaching rank 1.** It reaches rank 1
through the *type* route: "my college ID card" classifies as `id_card`, the corpus knows
`college_id.jpg` is one, and that agreement breaks the tie. Remove the type opinion and the
cap returns.

**q025 exists to keep that distinction measurable**, and it currently fails:

- Query: *"that rectangular plastic pass with my face printed on it"*
- Shares no token with `college_id.jpg`; verified not to trigger the `id_card` vocabulary
  (`identity card`, `student id`, `college id`, `employee id`)
- So neither filename nor `document_type` is a live route, and only CLIP can answer it
- **Result: rank 2, score 0.0164 = 1/(60+1)** — the cap, unchanged

Adding it dropped Recall@1 from 0.950 to 0.905. That is the correct direction: the row was
added *because* the system fails it, and without it the headline number implies a
capability that does not exist. It should stay failing until the cap is removed rather than
routed around.

**Open problem.** A principled fix has to let a strong image hit outrank a merely-adequate
text hit without ever comparing a CLIP similarity to a text one — the constraint that makes
this hard, and the reason a weighted sum is not available.

### 7.4 Chunk-draw damping: measured, and disabled

Scoring takes the best chunk per document, so a document contributing 40 chunks to the
window takes 40 draws and one contributing a single chunk takes one. The maximum of *n*
draws rises with *n* whether or not anything is more relevant, so **corpus share leaks into
the ranking as if it were evidence.** On this corpus one document holds **353 of 377 chunks
— 93.6%.**

Damping the per-document score by `log(draws)` at α = 0.05 made things clearly worse:
Recall@1 0.950 → 0.850, Recall@5 1.000 → 0.950, MRR 0.975 → 0.906. q016 fell from rank 1 to
rank 8 and out of the top five; q018 fell to rank 2. Both are rows that same calendar
*legitimately* answers, each on one event buried inside it — the single-decisive-chunk case
a size penalty is worst at.

**The bias is real and the correction is disabled at 0.0 rather than deleted**, because the
number is the evidence. The obstacle is that α cannot be chosen here: tuning it against the
gold set is fitting the test, and **the honest version needs a corpus that is not 93.6% one
document.** Four of twenty non-refusal rows expect that single file.

## 8. Methodology findings

These are results, not process notes. Each is a measured failure of a technique that looked
sound, and each generalises past this system.

### 8.1 A pre-registered prediction caught a regression the headline hid

*Source: `PHASE3.md`*

The first stage-1 implementation raised Recall@1 to 0.895 **while silently moving q007 from
rank 2 to outside the top 3.** The headline improved and a row regressed.

The cause was not the filter: stage 1 also *rewrote* the query, dropping the word carrying
the match.

| query embedded | rank | raw similarity |
|---|---|---|
| the user's own words | 2 | 0.547 |
| stage 1's rewrite | 4 | 0.509 |

**A correct filter still produced a worse result**, and without a written prediction naming
q007 specifically, the regression is invisible behind an improved aggregate. Stage 1 is now
trusted for filters and not for rewriting.

### 8.2 A guard that only fires at 100% is not a guard

*Source: `PHASE3C.md`, `MODEL-RISK.md`*

The evaluation harness refused to write a run only when **every** stage-1 call failed. It
caught two total quota outages — which is precisely what made it look sound — and then
passed a run in which **13 of 15 calls failed**: 87% dense-only under a stage-1 label.

The threshold is now 25%. **When writing a check against a degradation, ask what a partial
version of that degradation looks like.** The binary case is the easy one and rarely the one
that arrives.

### 8.3 Partial coverage hid a ranking defect completely

*Source: `POST-CLIP-FULL.md`, `LOCAL-TEXTGATED.md`*

Configurations 2 and 4 in §5 report the same Recall@1. With 3 of 8 images carrying vectors,
the image list was too sparse to displace anything and the numbers looked correct.
**Correct coverage is what made the defect measurable.**

A system shipped at partial coverage would have carried a latent ranking bug into every
later measurement without a symptom, until enough documents accumulated vectors to tip it —
with the cause months behind the effect.

### 8.4 An optimisation that was correct when written expired

*Source: `PHASE3B.md`*

The skip heuristic decides whether a query carries filterable signal. It was correct when
written: stage 1 returned source types, senders and dates, and "my passport" carries none.

Refusal then made `document_type` a fourth kind of signal the heuristic could not see. The
result was **refusal accuracy 0.000 with the extractor working perfectly** — q020 and q021
never reached stage 1, so there was no type to disagree with.

**Nothing broke. An assumption expired.** The two vocabularies now derive from one source,
with a structural test asserting it.

### 8.5 Listing a capability is not access to it

*Source: `MODEL-RISK.md`*

`models.list` returns `gemini-2.5-flash` for an API key that receives **404 "no longer
available to new users"** when it actually calls that model. Enumerate to discover; call to
confirm.

This is the third instance of the same shape in this project: an OCR engine that imported
cleanly and died at inference, a guard that reported healthy on an import check, and this.

---

### 8.6 A diagnosis asserted rather than checked shipped an inert fix

The tie-break in §7.2 was implemented, tested, measured — and changed nothing. Recall@1 came
back 0.900, exactly as before.

The cause was a claim made one step earlier: *"stage 1 correctly extracts
`document_type: id_card`, and the boost path discards it."* The second half was true. **The
first half was never checked.** `qwen2.5:3b` returns `document_type: None` for "my college
ID card", because the field is not in the schema's `required` list and a small model omits
what it may omit. The evidence actually in hand was that the *corpus* classifier had typed
the *file* — never that stage 1 had typed the *query*. Those are different claims about
different components, and one was substituted for the other.

The assertion was then repeated back in review and agreed with, which added confidence
without adding evidence. **Nothing in the reasoning caught it. The pre-registered prediction
did** — "q024 → rank 1" was written down before the run, and the run said 0.900 unchanged.
A diagnosis that cannot be wrong on paper can still be wrong on the machine.

The eventual fix is also better than the assumed one, and only because the assumption
failed: the query is classified by the **same vocabulary that classifies documents** — a
file typed from its filename, a query from its words, one table for both sides, no model in
the loop. Deterministic, free, and it cannot silently stop working when the model changes.
That option was never considered while the model was believed to be supplying the signal.

## 9. What is not measured

Stated plainly, because these are the limits an examiner should not have to discover.

**`document_identity` is now measured, and half of it fails.** `college_id.jpg` was added
to the corpus on 2026-09-04 and the gate reports `PASS` for the first time. q024 ("my
college ID card") reaches rank 1; **q025, which isolates the visual path, returns rank 2**
(§7.3). So the flagship type is covered, and the capability it is supposed to demonstrate —
finding a text-free document by appearance alone — is measured as *not working*. That is a
better position than the previous `NOT READY`, and a worse one than the headline Recall@1
suggests on its own.

The ID card ingested with **0 text chunks and 1 CLIP embedding**, confirming by measurement
what PRODUCT.md asserts: Tesseract reads nothing off laminated plastic.

**Visual absence is unsolved.** q022 and q023 are answered rather than refused (§6). No
mechanism in this system can report that a *picture* is absent.

**The hosted arm is not reproducible.** `gemini-2.5-flash` is closed to new API projects —
verified by call, not read from a changelog. **A reader with a new key cannot reproduce the
0.947.** They can reproduce the 0.895 by cloning the repository and running Ollama. The
dense baseline, the corpus vectors and all visual-search results are unaffected.

**Sample size.** 19 answerable rows means one row is 0.053 of Recall@1. Read the counts, not
the fractions, and do not read significance into a difference of one row.

**One corpus, one owner.** All measurements use a single personal archive of 14 documents.
The findings about fusion, extractor substitution and refusal are mechanical rather than
statistical, but they are not a distribution.

**Three corpus files contain no extractable text.** Two remain unfindable by description
even after visual search, because no gold query describes them.

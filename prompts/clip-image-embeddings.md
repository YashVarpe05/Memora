# CLIP image embeddings — searching by what a photo looks like

**Plan only. Nothing implemented.**

## The gap, stated as a fact about the pipeline

A photo of people contains no text. Tesseract returns an empty string. The upload route
rejects documents with no extractable text, so **no chunk row is created and no vector
exists**. The file is not ranked badly. It is not ranked.

Three files in `data/corpus/` are in this state right now, and every measurement report
since `BASELINE.md` has carried the line *"three corpus files contain no extractable text
and are unfindable by any query"*. That is not a retrieval quality problem and no amount of
query understanding touches it.

**Second reason, and the one that matters for the defence.** `document_identity` — the
flagship query type — has **zero gold rows and no working path**. Tesseract reads zero words
off a laminated college ID card; that was measured, and a wrong claim about it was corrected
once already. CLIP recognises "a photo of an identity card" from the picture, so the
flagship query gets a route that does not depend on OCR beating a reflective plastic
surface.

## Why CLIP and not a hosted vision model

**A hosted vision model would break architectural rule 1 outright.** Rule 1 forbids sending
document content to a model at layer one, and an image *is* the document. Sending the
Aadhaar photo to a captioning API to make it searchable would delete the project's strongest
privacy claim to fix a retrieval gap — and the masking pipeline, which exists to stop
identifier text leaving, would be bypassed entirely by shipping the picture of the
identifier instead.

CLIP runs locally. No API, no quota, no third party, no rule-1 violation. It is the rare
case where the private option is also the cheap one.

## The design

### Where the vectors live: a separate table

`chunks` holds text with `ordinal`, `page`, `contextual_prefix`, `token_count` and a
`memory_id`. An image embedding has none of those and is one-per-image, not many-per-
document.

**A new `image_embeddings` table**, not a nullable column bolted onto `chunks`:

```
id            uuid pk
user_id       uuid not null           -- RLS keys on it, like every other owned table
memory_id     uuid not null           -- fk to memories
embedding     vector(512)             -- CLIP ViT-B/32; NOT the 768 text dims
model         text not null           -- pinned, because changing it invalidates every row
created_at    timestamptz
```

Three reasons it is separate rather than a column:

1. **Different dimensionality.** CLIP ViT-B/32 is 512; the text index is 768. One pgvector
   index cannot serve both, and a nullable second vector column on `chunks` would mean every
   text chunk carries an unused 512-float column.
2. **Different distance semantics.** A CLIP text-image similarity of 0.28 is a strong match;
   the text pipeline treats 0.5 as weak. Mixing them in one column invites a threshold
   written for one to be applied to the other, which is this project's most repeated bug.
3. **Different lifecycle.** Re-embedding images on a model change must not touch text rows.

**RLS ships in the same migration that creates the table** — ENABLE + FORCE, with the
`NULLIF(current_setting('app.user_id', true), '')::uuid` policy. Non-negotiable per
`CLAUDE.md`, and the table is user-owned.

### How a text query searches both spaces

CLIP embeds text and images into **one shared space**, so the query is embedded twice, by
two different models, and searched in two indexes:

```
query ──┬─► gemini-embedding-001 (768) ─► chunks.embedding        ─► text hits
        └─► CLIP text encoder    (512) ─► image_embeddings.embedding ─► image hits
```

**Both searches run; neither is conditional on the other.** Deciding up front whether a
query is "visual" is another classifier, and this project has measured what a wrong
classifier costs.

### How results fuse: RRF, not score comparison

**The scores are not comparable and must never be compared.** CLIP cosine similarities for
genuine matches sit around 0.25–0.35; the text pipeline's sit around 0.5–0.8. A max() or a
weighted sum across them is meaningless, and would silently rank every text hit above every
image hit regardless of quality.

`RAG.md` already mandates **RRF at k=60** for fusing dense and BM25. The same mechanism
applies here, for the same reason — RRF consumes *ranks*, not scores, so it is indifferent
to two systems having different scales:

```
score(doc) = Σ over lists  1 / (60 + rank_in_that_list)
```

A document found by both text and image ranks above one found by either alone, which is
the desired behaviour for the ID card: OCR may catch a few words *and* it looks like a card.

**Filters and boosts apply after fusion, unchanged.** Stage 1's `source_types: [image]` is
already the right filter for image hits, so the existing machinery composes.

### What happens to the three unfindable files

They stop being rejected. Today the upload route refuses a document with no extractable
text; that rule exists because such a document was previously unsearchable, and that stops
being true. **The rule becomes: reject only if there is neither text nor an image
embedding.**

This is a real change to ingest, and it means those three files need re-ingesting. Cost:
three CLIP embeddings, local, free.

**It also has a measurement consequence that must not be missed.** `verify_corpus()`
currently reports those files as "on disk but rejected at ingest" and the harness treats
q019 as a deliberate control that must fail. **If images become ingestable, q019 stops being
a control and becomes a real row** — and the gold set needs a new control that is genuinely
absent, or the refusal work loses its baseline.

## Model size and CPU cost

**CLIP ViT-B/32**, the smallest useful variant:

| | |
|---|---|
| parameters | ~151M (vision + text towers) |
| download | ~340 MB fp32, ~170 MB fp16 |
| embedding dimension | 512 |
| image embed, CPU | ~50–150 ms per image, single-threaded |
| text embed, CPU | ~10–20 ms per query |
| RAM at inference | ~600 MB fp32 |

**These are order-of-magnitude figures from the model card and general CPU inference, not
measured on this hardware.** Given how often this project has been bitten by an unmeasured
number, the first implementation task is to measure them on the actual machine — the same
machine where PaddleOCR installed cleanly and could not run at all.

**Where it runs:** the OCR container already exists, already runs Python, and is already the
place heavy local models live. CLIP goes there rather than into the API process, so a
model load does not block request handling and a crash does not take down search.

**Query latency is the risk to watch.** Text embedding is ~15 ms, which is fine. But it is
added to a search that also pays stage 1's 2–3 s, so it disappears into the noise — the real
cost is ingest, at ~100 ms per image, and ingest is already slow and already batched.

## Predictions, before implementing

| # | prediction | reasoning |
|---|---|---|
| 1 | **The three text-free files become findable** by a description of what they show | This is the minimum bar. If it fails, the integration is broken, not the idea. |
| 2 | **q019 "that photo of me leaning on the balcony at college" flips from miss to rank 1** | It has been a miss in every run because its file is unindexed. It is a pure visual-recall query against a candid photo — the single best case for CLIP in the gold set. |
| 3 | **A `document_identity` row for the college ID card lands at rank 1**, once the card is in the corpus | The flagship. CLIP should recognise a card visually where Tesseract reads nothing. |
| 4 | **Recall@1 on the existing 19 rows does not fall below 0.947** | Fusion adds a list; it should not reorder rows that text already answers. |
| 5 | Fusion helps at least one row that already worked, by agreeing with it | Weakest prediction. Plausible for q001 and q007, which are images that also have text. |

### The control that must not improve

**q005 — "the list of drone topics i was supposed to learn"**, answer `mail.pdf`.

A four-page **text PDF with no visual character whatsoever**. CLIP has nothing to contribute
and its embedding of a page of prose should be uninformative. It is currently rank 1.

- **If q005 stays rank 1: expected.** Fusion did not disturb a row it has no business
  touching.
- **If q005 *improves* its score materially or its ranking changes**, CLIP is contributing
  signal where it cannot legitimately have any — most likely the image tower producing
  similar embeddings for all document-shaped rectangles, which would make it a
  "looks like a page" detector rather than a content matcher. That is a false-signal failure
  and it would mean image hits are polluting text results generally.

**A second control: q014, q016, q018 — the calendar rows.** The calendar has no images at
all. If any calendar row's ranking changes, fusion is affecting documents that have no
image embedding, which can only be a bug in how the two lists are merged.

## Files that would change

**Create**
```
services/image_embedding.py          CLIP client, talks to the OCR container
db/models/image_embedding.py
repositories/image_embedding.py      scoped, like every repository
migrations/versions/0005_image_embeddings.py   + RLS in the same migration
tests/test_image_embedding.py
tests/test_fusion.py
```

**Modify**
```
api/routers/uploads.py     embed images at ingest; stop rejecting text-free images
services/search.py         second list + RRF fusion
docker/ocr/                CLIP model alongside tesseract
eval/baseline.py           report which hits came from which list
docs/GOLD.jsonl            document_identity rows, and a replacement absence control
```

## Acceptance

1. The three text-free files are findable by description.
2. Text-only rows are unchanged — q005 and the calendar rows checked **by name**, not
   inferred from the headline.
3. Scores from the two spaces are **never** compared numerically anywhere in the code.
4. `image_embeddings` has FORCE RLS from its creating migration, proven by a raw-SQL test
   with no WHERE clause, as `CLAUDE.md` requires.
5. No image is sent anywhere off the machine. A test asserts the CLIP path makes no
   outbound request beyond the local container.
6. Timings measured on this hardware and written down, not quoted from this plan.

## Risks

**The dimension mismatch is a trap.** `MaskedText` and the 768-dim embedder are threaded
through the codebase. A 512-dim vector entering a function expecting 768 will fail loudly in
pgvector but may fail silently in Python if a list is passed around untyped.

**CLIP is weak at text-in-images.** It recognises "a document" but reads few words. It
complements OCR and does not replace it — where OCR works, OCR remains better, and the
fusion has to reflect that rather than letting a vague visual match outrank an exact text
hit.

**The absence control problem is the sharpest risk**, because it is easy to miss: making
images ingestable silently converts q019 from a control into a normal row, and the refusal
work depends on having rows that genuinely cannot be answered. New controls must land in the
same change, not afterwards.

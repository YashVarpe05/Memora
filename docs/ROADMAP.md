# Roadmap

Sequencing and ownership. Architecture detail lives in the per-phase docs, which land
in the week their phase starts — see the note at the bottom.

Resequenced after the product reframe: the primary use case is document retrieval, and
most target documents are photos with no text layer. `docs/PRODUCT.md` is the authority
on what the product is; this file is the authority on the order it gets built in.

---

## Done

| | |
|---|---|
| Vertical slice | PDF → chunks → pgvector → grounded answer with chunk IDs |
| Row-level security | Shipped early, in the migration that created the tables |
| PWA shell | Layout, routing, design tokens, chat UI against mocked responses |

---

## Parallel now

| Track | Owner | Done when |
|---|---|---|
| Corpus exports | Adi | Calendar `.ics`, email `.eml` exports, WhatsApp chat `.txt`, camera photos with EXIF intact. **Not unblocked by OCR — still yours to collect** |
| Google OAuth setup | backend | Consent screen configured, scopes declared, test users added |
| UML | docs | Six diagrams. The ingestion and query **sequence** diagrams are the two that carry weight |
| PWA shell polish | frontend | Continues against mocks until `/search` exists |

The corpus is 10 files. The gate needs 20 queries across 8 types, and
`temporal_resolution` has nothing to anchor to without a calendar export. OCR unblocks
*writing* the queries; it does not collect the files.

---

## Reclaimed scope — do not refill

Audio ingestion, Whisper, and the arq job queue **left the critical path** when the
product reframed to document retrieval. No hero query in `PRODUCT.md` needs audio any
more; the old HR-interview case is now a layer-two example.

This is the only place the reframe gave time back. **It goes to OCR quality and the
document viewer.** Not to new features, not to a nicer chat, not to another connector.
Reclaimed time that gets refilled with scope was never reclaimed.

---

## Phases, in order

| # | Phase | Done when |
|---|---|---|
| 1 | **OCR + PII masking** | Images are searchable. Aadhaar and PAN patterns masked before embedding. `uv run python -m memora.eval.inspect` shows **extracted text for every image in `data/corpus/`** |
| 2 | `/search` — ranked documents | Chunk scores aggregate to a document score; two chunks from one PDF are one result. Thumbnails generated at ingest. **No generation call** |
| 3 | Gold set + baseline recorded | Harness on the new taxonomy. Naive dense Recall@1 and MRR@10 committed, failures included |
| 4 | **Query understanding** | Two-stage retrieval from `PRODUCT.md`. Measured against the recorded baseline |
| 5 | Auth | Dev UUID replaced by a verified token. RLS already enforces the isolation |
| 6 | Gmail connector | Live ingest. OAuth stays in Testing mode with test users |
| 7 | Layer two + audio | Streaming chat, citation hover, span highlight, Whisper, arq |

### Parallel frontend track — starts when phase 2's contract lands

Ranked result list, thumbnails, in-app viewer (page a PDF, zoom an image), download.

Buildable against `openapi.json` the moment `/search` exists. **This is not polish.** The
answer is the file, and a file you cannot open is not an answer. It runs alongside phases
3–5 rather than waiting behind them.

### Why OCR is first

One dependency chain drives the whole order:

```
OCR  →  inspector shows real image text  →  gold set  →  baseline  →  query understanding
```

Recording the baseline used to need only text PDFs. Under Recall@1 over files it needs
images searchable — six of ten corpus files are images, and the flagship query targets
one. Writing the gold queries needs to know what is *in* those images, which is the
inspector's job and it cannot do it today.

The gold set was never blocked on one person's afternoon alone. It was partly blocked on
OCR, and that went unnoticed for several sessions.

`mail.pdf` is the case already in hand: four pages, zero extractable text.

### Protect phase 4

It is the difference between Memora and a search box, and it is the phase most likely to
get squeezed when the phases around it run long.

**Phase 4 does not start until the phase 3 baseline is recorded and committed.** Run the
gold set against naive dense retrieval and commit the numbers, including the failures.

- An ablation table needs a number taken *before* the improvement, not reconstructed
  after it.
- A committed baseline is timestamped. A baseline re-run later, against a pipeline that
  has quietly changed, is not a baseline.

Those failures are a result worth reporting, not an embarrassment to fix before anyone
sees them. They are the evidence that query understanding was necessary.

### OCR benchmark — rescoped

Un-parked: OCR is the critical path now, so which engine wins actually matters.

**Answered early, and not as expected.** PaddleOCR cannot run on this hardware at
all - it dies in a oneDNN kernel at inference, in the Linux container as well as on
Windows. Tesseract is the only working engine, so there is no engine comparison to
make: OCR quality is whatever tesseract achieves. The benchmark's remaining value is
measuring *that*, and the first measurement is already in: a laminated ID card
photographed by a camera yields zero words across twelve rotation and
page-segmentation combinations.

**Runs on `data/corpus/` only.** No separate 20-image set, no hand-written transcripts —
the corpus images are the images that will actually be searched.

Without reference transcripts there is no CER, so the comparison changes shape:
**engines are judged by downstream Recall@1 on the gold set.** Which engine makes the
Aadhaar card findable is the question that matters, and it is measured with the metric
the project already reports. CER on a handful of hand-checked images stays available as
a spot-check, not as the headline.

### Future work — images with no text

OCR finds text. It does not describe pictures. A photo of a bike, a landscape, or an
undiagrammed whiteboard extracts nothing and is therefore unfindable, however good the
retrieval gets. Two files in the current corpus already behave this way.

"Find the photo of my bike" is a real personal-memory query and it needs a different
mechanism: a vision model captioning images at ingest, so there is text to embed.

Not scheduled. Recorded so it is a decision someone makes rather than a gap someone
discovers.

Two related known weaknesses: handwriting, where tesseract is poor and paddle is
better but still unbenchmarked behind its build arg; and audio, which left the
critical path with Whisper, so voice notes are currently unsearchable.

### Cut order, from PRODUCT.md

reranking → query transformation → extra connectors → entity resolution → native app

**Never cut:** OCR, Gmail connector, query understanding, ranked file results with viewer
and download, per-owner isolation, the evaluation harness.

---

## Renumbering

Phase numbers changed. Older comments in the codebase still use the previous ones:

| old | was | now |
|---|---|---|
| 1 | Vertical slice | Done |
| 2 | Schema + RLS + auth | RLS done; auth is **5** |
| 3 | Query understanding | **4** |
| 4 | Ingestion — OCR, Whisper, arq | OCR is **1**; Whisper and arq are **7** |
| 5 | Frontend for real | Viewer and download are the **parallel track**; chat polish is **7** |
| 6 | Gmail connector | **6** |

Around twenty comments across the API and web source still carry old numbers — most say
"phase 4" for OCR or "phase 3" for query understanding. They are corrected as each phase
is worked on, not in a sweep.

---

## Documents land per phase

`SCHEMA.md` (phase 5), `RAG.md` (phase 4), `PORTABILITY.md` (parallel frontend track).
Deliberate: loading the full architecture before the code exists means it gets
half-remembered and unfollowed. Absence of a doc here is not an oversight.

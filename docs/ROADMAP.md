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

## Retrieval is done. Stop tuning it.

**After phase 3d and refusal, no further work on retrieval quality.** Not reranking, not
prompt iteration, not additional ablations, not threshold calibration. Those become
**documented future work** and go in the report as such.

This is written down because the failure mode is specific and likely: retrieval is the part
with a harness, a gold set, and a number that moves. It is *satisfying* to work on. A future
session that opens this repo will find a measurement loop that rewards effort immediately,
and two large capabilities that do not — and it will drift back to the number.

**The number already crossed its threshold.** Recall@1 0.947 against a 0.842 baseline,
reproduced three times, with pre-registered predictions and a silent-failure guard that
caught two real outages. That is a strong report chapter and it is finished.

**What is left are capability gaps, not quality gaps.** No amount of retrieval tuning makes
a photo with no text findable, and none of it lets the app see a file the user has not
uploaded. Two of the product's three sentences are unbuilt:

| sentence | status |
|---|---|
| "find my fee receipt when the filename is `doc_8837.pdf`" | **built, measured** |
| "it searches the files already on my device" | **not built — zero lines** |
| "find the group photo" | **not built — zero lines** |

**The only retrieval work that survives this rule is refusal**, and it is included because
it is the last failing acceptance criterion rather than an improvement: typing nonsense
currently returns ten results, and someone will do that during the defence. One day, then
stop.

### Order after that, and why

1. **CLIP** — unblocks hero query 7 and gives `document_identity` a path that does not
   depend on Tesseract reading laminate, which it cannot
2. **Capacitor + device indexing** — the largest unbuilt thing in the project, and what
   makes sentence 2 true
3. Auth, report, UML

**If time runs out during Capacitor**, the project still has measured retrieval, a working
UI, visual search, the privacy architecture, and an honest chapter on why a native shell is
required and what it would take. That is a complete submission. What is *not* a complete
submission is a further-optimised retrieval number next to two unbuilt sentences.

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

### Two phases promoted out of "future work"

Both were optional. Both are now **core**, because each one decides whether a sentence in
`PRODUCT.md` is true. Numbered separately because their position in the order is a
scheduling decision that has not been made yet — see the sizing note below.

| # | Phase | Done when | Plan |
|---|---|---|---|
| C | **CLIP image embeddings** | A text query matches a document by what it looks like. The three text-free corpus files become findable. `document_identity` has a path that does not depend on OCR | `prompts/clip-image-embeddings.md` |
| D | **Capacitor + device indexing** | The app enumerates device storage and indexes what it finds, without the user uploading anything | `prompts/capacitor-device-indexing.md` |

**Why Capacitor stopped being optional.** It sat in "cut in this order" as *native app*,
last. That was correct when the product was "upload your documents and search them". It is
wrong now that the product is "search the files already on your phone", because **a PWA
cannot enumerate device storage** — browsers sandbox it deliberately, and no web API exposes
a gallery or a Downloads folder for scanning. Without a native shell the product sentence is
false. That is a platform boundary, not an engineering gap.

**Why CLIP stopped being optional.** Hero query 7, "the group photo", has no text anywhere.
OCR returns an empty string, so no chunk and no vector are ever created and the file is not
ranked badly — it is absent. Three corpus files are already in this state.

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
measuring *that*, against real corpus documents.

No ID-card measurement exists yet. An earlier note here reported one; the file tested
was a candid photo containing a lanyard rather than a photograph of a card, so the
result measured nothing about cards.

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

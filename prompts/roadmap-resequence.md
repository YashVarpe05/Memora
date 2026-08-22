# Roadmap resequence — OCR to the critical path

**Status: plan only. `docs/ROADMAP.md` is unchanged pending approval.**

## Goal

Resolve the OCR disagreement between `PRODUCT.md` and `ROADMAP.md` in favour of
`PRODUCT.md`, and place the work the document-retrieval reframe newly owes.

## What I read

- `docs/PRODUCT.md` — as rewritten in `79b9989`: two layers, Recall@1, architectural rules
- `docs/ROADMAP.md` — current order 1→2→3→4→6→5
- `prompts/product-document-retrieval.md` — the approved reframe and taxonomy
- `apps/api/src/memora/services/retrieval.py` — chunk-level ranking, uncalibrated threshold
- `apps/api/src/memora/eval/{retrieval,inspect}.py` — the gate and the corpus inspector
- `apps/api/src/memora/bench/ocr.py` — parked benchmark, 20 images + transcripts owed
- Live state: migration `0001` already ships RLS; slice done; PWA shell on mocks

## Assumptions

**1. The baseline dependency changed shape, and that is what drives the reorder.**
The constraint "record the baseline before building query understanding" used to need
only text PDFs. Under Recall@1 over files, the baseline cannot be measured until images
are searchable — six of the ten corpus files are images, and the flagship query targets
one. **OCR is now upstream of the baseline, and the baseline is upstream of query
understanding.** That single chain does most of the resequencing.

**2. Frontend splits in two, and only half is late.** "Frontend for real" was one late
phase. Ranked results, thumbnails, viewer and download are now the product's face — the
answer *is* the file, and a file you cannot open is not an answer. Streaming chat and
citation hover remain layer-two polish. Treating these as one phase would either drag
polish forward or leave the flagship demo with no viewer.

**3. Whisper and audio leave the critical path entirely.** No hero query in the rewritten
`PRODUCT.md` needs audio. The old q002 (HR interview) was the audio case and it is now a
layer-two example. This is a de-scope, not a deferral — worth noticing, because it is the
only place the reframe gave time back.

**4. Synchronous OCR is enough to reach the baseline.** A 10–30 file demo corpus does not
need arq to be OCR'd. Background jobs can arrive with audio. If you would rather not
build ingestion twice, say so and arq moves up with OCR.

**5. RLS is already done.** It shipped in migration `0001` with the tables. Phase 2 as
written is now only auth.

## Proposed order

### Done

| | |
|---|---|
| Vertical slice | PDF → chunks → pgvector → grounded answer with chunk IDs (`e4ad570`) |
| RLS | Shipped early, in the migration that created the tables |
| PWA shell | Layout, routing, tokens, chat against mocks |

### Critical path

**1. OCR + PII masking.** Images become searchable. Ships with Aadhaar/PAN masking in the
same phase, per the `PRODUCT.md` rule — OCR must not land without it. Runs in a Linux
container: Paddle installs on Windows and then dies in a oneDNN kernel, and the ingestion
worker is a container in production anyway, so the Windows number was measuring the wrong
environment.

*Why first:* without it the flagship query returns nothing, and nothing downstream can be
measured.

**2. `/search` — ranked documents, no LLM.** Chunk scores aggregate to a document score;
two chunks from one PDF are one result. Thumbnails generated at ingest. No generation
call, per the architectural rule.

*Why second:* this is the layer-one contract. Every measurement and every UI reads it.

**3. Gold set + baseline recorded.** Harness moves to the new taxonomy, Recall@1 and
MRR@10. Naive dense numbers committed, including the failures.

*Why here:* the last point where a baseline is still honest. After step 4 there is
nothing to compare against.

**4. Query understanding.** The protected contribution, unchanged in priority and now
measurable against a recorded number.

**5. Auth.** RLS already enforces isolation; this swaps the dev UUID for a verified token.

**6. Gmail connector.** Non-cuttable. Stays ahead of layer-two polish.

**7. Layer-two polish + audio.** Streaming chat, citation hover, span highlight, Whisper,
arq.

### Parallel frontend track — starts once step 2's contract is committed

Ranked result list, thumbnails, in-app viewer (page a PDF, zoom an image), download.
Buildable against `openapi.json` the moment `/search` exists, and it is what the demo
shows. Not on the critical path, but not late either.

## Orphaned or duplicated by the change

**The OCR benchmark is un-parked but should shrink.** It was parked as off the critical
path; OCR is now the critical path, and choosing between engines actually matters. But it
asked for a *separate* 20-image set with hand-written transcripts, and the corpus images
are now the same images. **Proposal: benchmark on the corpus images only.** One collection
effort instead of two, and it measures the engine on the documents that will actually be
searched.

**Whisper and arq are orphaned from the critical path.** See assumption 3. Real time back.

**`multimodal` as a gold type is already retired** by the approved taxonomy, replaced by
`answer_modality`. No further action; noting it so it is not re-added.

**`MIN_SIMILARITY_UNCALIBRATED` changes meaning.** It gated "call the LLM or refuse." Under
layer one it gates "is the top-ranked document good enough to show." Same constant, new
semantics, still uncalibrated — and it must now be swept against Recall@1 rather than
against a chat refusal.

**`/chat` citations now owe a document link.** Layer two must open the same viewer layer
one uses. Small overlap, worth building once.

**The corpus inspector cannot preview images** — every image row currently reads
*"text content unknown until OCR runs in phase 4"*. You expected the previews to tell you
whether the WhatsApp screenshots support OCR-dependent gold queries. **They cannot.** That
was acceptable when images were peripheral; they are now the flagship. Proposal, flagged
not built: run OCR inside `memora.eval.inspect` so image rows carry real extracted text.
It makes the gold-set session possible for exactly the files that matter most, and it
depends on step 1.

## Acceptance criteria

1. `ROADMAP.md` places OCR first on the critical path with PII masking in the same phase.
2. Query understanding stays protected, and sits immediately after the recorded baseline.
3. The baseline step explicitly precedes query understanding.
4. Gmail remains on the never-cut list and ahead of layer-two polish.
5. Viewer, download, thumbnails and ranked results appear as a parallel frontend track.
6. Whisper and arq are visibly de-scoped from the critical path, not silently dropped.
7. The OCR benchmark is un-parked and rescoped onto the corpus images.
8. No code, gate, or `PRODUCT.md` changes.

## Checks to run

```
cd apps/api && uv run pytest && uv run ruff check .
git diff --stat
```

`git diff --stat` should show `docs/ROADMAP.md` and nothing else.

## How to verify

Read `ROADMAP.md` and check that the dependency chain reads forwards: OCR makes images
searchable, `/search` makes documents rankable, the baseline measures that, and query
understanding improves on a number that already exists. If any step could be swapped with
the one before it without breaking something, the ordering is decorative.

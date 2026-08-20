# Roadmap

Sequencing and ownership. Architecture detail lives in the per-phase docs, which land
in the week their phase starts — see the note at the bottom.

---

## Parallel now — nothing here waits on the gate

| Track | Owner | Done when |
|---|---|---|
| Corpora + gold set | all four | `data/corpus/` has 15-20 real files each, `docs/GOLD.jsonl` rewritten, eval prints `PASS` |
| OCR benchmark | ingestion | CER table for PaddleOCR vs Tesseract vs Gemini Flash vision over 20 images, measured with `jiwer` |
| UML | docs | Six diagrams. The ingestion and query **sequence** diagrams are the two that carry weight |
| PWA shell | frontend | Layout, routing, tokens, chat UI against mocked responses, typed from `openapi.json` |

Everyone writes queries against **someone else's** corpus. That separation is the answer
when an examiner asks whether the same person designed the test and the system.

---

## Phases, in order

| # | Phase | Done when |
|---|---|---|
| 1 | Vertical slice | One PDF in, one grounded answer with a citation out. No auth, no queue, no frontend |
| 2 | Schema + RLS + auth | Every user-owned table has its RLS policy in the same migration, with a cross-user test |
| 3 | **Query understanding** | Two-stage retrieval from PRODUCT.md. `q001` and `q002` start passing |
| 4 | Ingestion pipeline | OCR, Whisper, arq workers, progress reporting |
| 5 | Frontend for real | Streaming chat, citation hover, click-to-source with the span highlighted |
| 6 | Gmail connector | Live ingest from Gmail. OAuth stays in Testing mode with test users |

### Protect phase 3

It is the difference between Memora and a document chatbot, and it is the phase most
likely to get squeezed when 4 and 5 run long. A pipeline that goes straight to vector
similarity fails `q001`, `q002` and `q004` while looking excellent on generic content
questions — which is the failure that looks like success right up until the defence.

### Cut order, from PRODUCT.md

reranking -> query transformation -> extra connectors -> entity resolution -> React Native

**Never cut:** Gmail connector, query understanding, citations, per-user isolation, the
evaluation harness.

### Open risk: phase 6 is non-negotiable but scheduled last

Gmail sits after the two phases most likely to overrun, yet it is on the never-cut list.
PRODUCT.md is explicit that upload-only makes this NotebookLM. Two mitigations, whichever
suits: pull the OAuth consent screen and test-user setup forward into any phase (it is
configuration, not code, and has lead time), or move the connector ahead of phase 5 so
the demo-critical path finishes before the polish work starts.

---

## Documents land per phase

`SCHEMA.md` (phase 2), `RAG.md` (phase 3), `PORTABILITY.md` (phase 5). Deliberate: loading
the full architecture before the code exists means it gets half-remembered and unfollowed.
Absence of a doc here is not an oversight.

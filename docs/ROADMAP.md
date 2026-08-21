# Roadmap

Sequencing and ownership. Architecture detail lives in the per-phase docs, which land
in the week their phase starts — see the note at the bottom.

---

## Parallel now — nothing here waits on the gate

| Track | Owner | Done when |
|---|---|---|
| **Gold set** | Adi, solo | 15 real files in `data/corpus/`, `docs/GOLD.jsonl` rewritten against them, eval prints `PASS`. **Blocks phase 1** |
| Google OAuth setup | backend | Consent screen configured, scopes declared, test users added. **Start today** |
| ~~OCR benchmark~~ | parked | Harness is built and red. Needs 20 images *and* 20 hand-written transcripts - tedious, not on the critical path, competing with the gate |
| UML | docs | Six diagrams. The ingestion and query **sequence** diagrams are the two that carry weight |
| PWA shell | frontend | Layout, routing, tokens, chat UI against mocked responses, typed from `openapi.json` |

**The gold set is one person's two hours, not a team meeting.** 15 files, 20 queries
written by working backwards from each file. Nothing else waits on scheduling.

Cross-corpus review - each person writing queries against someone *else's* files - is a
credibility improvement to the eval set, added whenever the team next meets. It is the
answer when an examiner asks whether one person wrote both the test and the system. It
was never a prerequisite for code, and treating it as one is what kept this blocked for
five sessions.

OAuth setup is an hour of clicking with unpredictable lead time — Google sometimes sits
on a consent screen for days with no visible reason. It blocks nobody, so it starts now
rather than being discovered in Week 10.

---

## Phases, in order

| # | Phase | Done when |
|---|---|---|
| 1 | Vertical slice | One PDF in, one grounded answer with a citation out. No auth, no queue, no frontend |
| 2 | Schema + RLS + auth | Every user-owned table has its RLS policy in the same migration, with a cross-user test |
| 3 | **Query understanding** | Two-stage retrieval from PRODUCT.md. `q001` and `q002` start passing |
| 4 | Ingestion pipeline | OCR, Whisper, arq workers, progress reporting |
| 6 | Gmail connector | Live ingest from Gmail. OAuth stays in Testing mode with test users |
| 5 | Frontend for real | Streaming chat, citation hover, click-to-source with the span highlighted |

**Phase 6 runs before phase 5, deliberately.** Numbers kept as-is so they still match
how the phases are referred to elsewhere.

### Why the connector jumps the frontend

Gmail is on the never-cut list but was scheduled behind the two phases most likely to
overrun. Pulling OAuth setup forward removes the unpredictable wait; resequencing removes
the schedule risk. They solve different problems, so both apply.

It also gives a better fallback shape. If phase 5 gets squeezed, the demo is a slightly
rough frontend over a working connector — which still proves the thesis. The reverse does
not: a polished UI over upload-only is the NotebookLM problem, dressed better.

### Protect phase 3

It is the difference between Memora and a document chatbot, and it is the phase most
likely to get squeezed when the phases around it run long. A pipeline that goes straight
to vector similarity fails `q001`, `q002` and `q004` while looking excellent on generic
content questions — the failure that looks like success right up until the defence.

**Phase 3 does not start until the naive baseline is recorded and committed.** Run the
gold set against phase 1/2 retrieval — dense-only, no query understanding — and commit
the numbers, including `q001` and `q002` failing. Two reasons:

- An ablation table needs a number taken *before* the improvement, not reconstructed
  after it. Build phase 3 first and there is nothing to compare against.
- A committed baseline is timestamped. A baseline re-run later, after the pipeline has
  quietly changed, is not a baseline.

Those failures are a result worth reporting, not an embarrassment to fix before anyone
sees. They are the evidence that query understanding was necessary.

### Cut order, from PRODUCT.md

reranking -> query transformation -> extra connectors -> entity resolution -> React Native

**Never cut:** Gmail connector, query understanding, citations, per-user isolation, the
evaluation harness.

---

## Documents land per phase

`SCHEMA.md` (phase 2), `RAG.md` (phase 3), `PORTABILITY.md` (phase 5). Deliberate: loading
the full architecture before the code exists means it gets half-remembered and unfollowed.
Absence of a doc here is not an oversight.

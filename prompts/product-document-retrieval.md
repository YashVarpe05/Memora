# Product reframe — document retrieval is layer one

**Status: plan only. PRODUCT.md is unchanged. Gate and roadmap untouched, as instructed.**

## Goal

Rewrite `docs/PRODUCT.md` so the primary use case is finding and opening a specific
document — "find my Aadhaar card" — with grounded chat demoted to a second layer.

## What I read

- `docs/PRODUCT.md` — problem statement, hero queries, retrieval contract, novelty claims
- `docs/ROADMAP.md` — phase order (OCR currently phase 4)
- `CLAUDE.md` — retrieval rules, security rules, out-of-scope list
- `apps/api/src/memora/repositories/chunk.py` — `search_dense` returns chunks, not files
- `apps/api/src/memora/eval/retrieval.py` — the seven types the gate enforces
- Live corpus via `memora.eval.inspect`: 6 images, 4 PDFs, one of which (`mail.pdf`)
  has no text layer at all

## Assumptions

**1. "The answer is the file" changes the retrieval unit, not just the UI.** Today
`search_dense` ranks chunks. File retrieval has to aggregate chunk scores up to a
document score and rank documents. Two chunks from one PDF are one result, not two.
This is an API shape change, so I am assuming a new `/search` endpoint rather than
reshaping `/chat` — that keeps the chat contract already generated into `packages/core`
valid.

**2. Modality stops being a query type and becomes a property of the answer.** Almost
every target document is a photo or screenshot, so `multimodal` no longer distinguishes
anything. Proposed below as a separate per-row field so coverage stays measurable.

**3. `must_refuse` changes meaning, and this one matters.** Today q006 is "what is my
bank account number" and the correct response is refusal. The new product says "find my
Aadhaar card" and the correct response is the file. Those look contradictory. They are
not, once refusal is defined as **the document is not in your corpus** rather than **the
topic is sensitive**. Retrieving your own stored Aadhaar card is success. Inventing an
Aadhaar number you never stored is the failure. PRODUCT.md has to say this explicitly or
the gold set will encode the wrong rule.

**4. Recall@1 replaces faithfulness as the primary metric,** with faithfulness applying
to layer two only. This takes the LLM-judge out of the primary number, which is the
single biggest reliability improvement available to the evaluation.

**5. I am not touching the gate or the roadmap,** so PRODUCT.md will *flag* that OCR is
phase-1 critical without reordering `docs/ROADMAP.md`. The two files will disagree until
you approve a roadmap change. Deliberate, but worth knowing.

## Files that will change

```
docs/PRODUCT.md    rewritten - problem, hero queries, retrieval contract,
                   definition of working, scope, novelty claims
```

Nothing else. No code, no gate, no roadmap.

## Implementation requirements

**Problem statement.** Rewritten around a document you own, on your own devices, that
you cannot locate — Aadhaar, PAN, marksheet, admit card, fee receipt, plus the existing
professor-PDF case. The failure being solved is: filed somewhere, findable by nothing.

**Hero queries**, rewritten as file retrieval:

| # | Query | What makes it hard |
|---|---|---|
| 1 | "find my Aadhaar card" | A photo with no text layer. Fails completely without OCR, and the query carries no content signal beyond the document kind |
| 2 | "the PDF a professor sent" | Pure metadata: sender role, file type, attachment |
| 3 | "the fee receipt from last semester" | Vague time phrase must resolve to a range first |
| 4 | "the screenshot with the database error" | Remembered by appearance; the text exists only inside pixels |
| 5 | "my 10th marksheet", with three marksheets stored | Disambiguation — the right one at rank 1, not a pile |
| 6 | "find my passport", never stored | Must refuse. Absent, not sensitive |

Layer two keeps "what did HR say during the internship interview" — an answer about
content, with citations.

**Retrieval contract.** Two stages stay. Stage 2 now returns ranked *documents* with
per-document best-chunk evidence, not a flat chunk list.

**What working means.** The correct file at rank 1. The user sees a thumbnail,
recognises it, opens it in-app, pages a PDF, zooms an image, and downloads it.

**Metrics.** Recall@1 primary, MRR@10 secondary, refusal accuracy for absent documents.
Answer faithfulness applies to layer two only and is explicitly secondary.

**Scope additions.** Document viewer, download, result thumbnails, ranked file results.

**OCR flag.** A note stating OCR is phase-1 critical because most target documents are
photos and screenshots, pointing at `mail.pdf` in the corpus as the case already in hand.
Flag only — the roadmap keeps its current order until you say otherwise.

## Security requirements

Making an Aadhaar card the flagship document raises two things that were not issues when
the product was chat over notes.

**1. OCR text of an identity document contains the identity number.** Once an Aadhaar
photo goes through OCR, the extracted text holds the actual number. That text is then
embedded and stored — and embedding today is a Gemini API call, so the number leaves the
machine.

Proposed mitigation, flagged not built: **mask detected identifiers before embedding.**
Aadhaar is 12 digits, PAN is `ABCDE1234F`; both are trivially detectable. Store masked
text for retrieval and keep the raw number only in the original file, which never leaves
local storage. The document stays findable by type, issuer and context, and the number
is never sent anywhere. Cheap, demonstrable, and it turns novelty claim 2 from an
architecture argument into something visible on stage.

**2. Layer one should not need an LLM at all.** Finding a file is retrieval plus ranking.
If `/search` returns ranked documents with no generation call, an Aadhaar card can be
found without any part of it entering a third-party prompt. Only layer-two chat involves
the model, and the user chooses to invoke it. Worth stating in PRODUCT.md as a design
commitment rather than letting it fall out by accident.

Neither is a blocker. Neither is mine to decide alone.

## Proposed gold-set taxonomy — for review, not for the gate

The current seven were designed for chat. `cross_source` assumed an answer spanning
several sources; a file answer is one file. `multimodal` described nearly every row.

| type | means | example |
|---|---|---|
| `document_identity` | names the document by kind | "find my Aadhaar card" |
| `metadata_only` | sender, type, date only — zero content | "the PDF a professor sent" |
| `temporal_resolution` | time phrase resolves before search | "the fee receipt from last semester" |
| `visual_recall` | remembered by how it looked | "the screenshot with the red error" |
| `entity_resolution` | a person, possibly named inconsistently | "the letter from Prof. Kulkarni" |
| `content_semantic` | remembered by what it says | "the doc about vector databases" |
| `disambiguation` | several plausible matches, one is right | "my 10th marksheet" |
| `must_refuse` | not in the corpus at all | "find my passport" |

Changes from today: `semantic` becomes `content_semantic`; `cross_source` becomes
`disambiguation`; `multimodal` is dropped as a type; `document_identity` and
`visual_recall` are added.

Two new per-row fields:

- `answer_modality`: `pdf | image | audio | text | email` — lets the gate require
  coverage across modalities separately from query type, which is what `multimodal` was
  actually trying to do.
- `expected_rank`: defaults to 1, making Recall@1 checkable per row.

This invalidates the eight placeholder rows in `docs/GOLD.jsonl` and would change
`KNOWN_TYPES` in the harness. **Neither happens until you approve the taxonomy.**

## Acceptance criteria

1. PRODUCT.md leads with document retrieval; chat is visibly the second layer.
2. All six hero queries are file-retrieval shaped, and the refusal case survives.
3. Recall@1 and MRR are named primary; faithfulness is named secondary.
4. Viewer, download, thumbnails and ranked results appear in scope.
5. The OCR flag is present and says why.
6. Refusal is defined as absent, not sensitive.
7. No other file changes.

## Checks to run

No code changes, so the code gates are unaffected. Confirming that is the check:

```
cd apps/api && uv run pytest && uv run ruff check .
git diff --stat
```

`git diff --stat` should show `docs/PRODUCT.md` and nothing else.

## How to verify

Read `docs/PRODUCT.md` top to bottom and ask whether someone who has never seen this
conversation would build a file finder from it, or a chatbot. If any section still reads
chatbot-first, it has not landed.

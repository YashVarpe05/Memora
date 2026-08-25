# Memora AI — Product Definition

*Read this before writing any code. This file defines what "working" means.*

---

## The problem

You own the document. It is on one of your devices. You still cannot find it.

Aadhaar card, PAN card, 10th marksheet, admit card, fee receipt, the offer letter, the
PDF a professor sent. Each one arrived through a different app — WhatsApp, Gmail, a
camera roll, a downloads folder — and each app searches only its own silo, only by
filename or keyword.

Two things make this fail in exactly the wrong moment:

**You remember the document, not its filename.** You think "my Aadhaar card," not
`IMG_20240817_113244.jpg`. You remember who sent it, roughly when, and what kind of thing
it is. Nothing on your device is indexed that way.

**Most of these documents are photographs.** An Aadhaar card is a phone photo. A
marksheet is a scan. A fee receipt is a screenshot. There is no text layer, so keyword
search over them returns nothing — not poor results, nothing at all.

**Memora accepts a human-shaped description of a document and returns the document.**

---

## Two layers

Everything in this project sits in one of these, and they are not equally important.

**Layer one — find the file.** You describe it, Memora ranks your documents and shows
them. You recognise the right one from its thumbnail, open it, and download it. **The
answer is the file.** This is the product.

**Layer two — ask about the contents.** "What did HR say during the internship
interview." A grounded answer with citations back into the source. This is real and it
stays, but it is built on top of layer one, not instead of it.

If layer one does not work, layer two is a chatbot over a folder.

---

## The hero queries

These are the acceptance tests for the entire project. If these don't work, nothing else
matters. Queries 1–5 are layer one: **success is the correct file at rank 1.**

| # | Query | What makes it hard |
|---|---|---|
| 1 | "find my Aadhaar card" | A phone photo with **no text layer**. Without OCR the system cannot find it at all — not badly, at all. The query also carries no content signal beyond the kind of document it is. |
| 2 | "the PDF a professor sent" | **No content in the query.** Pure metadata: sender role, file type, attachment. Vector search alone returns noise. |
| 3 | "the fee receipt from last semester" | **Vague temporal reference.** "Last semester" must resolve to a date range before any content search is meaningful. |
| 4 | "the screenshot with the database error" | Remembered by **how it looked**. The text exists only inside pixels, and the description is approximate. |
| 5 | "my 10th marksheet", with three marksheets stored | **Disambiguation.** Several documents plausibly match. The right one has to be first, not somewhere in a pile. |
| 6 | "find my passport", never stored | **Must refuse.** See the refusal rule below. |
| 7 | "the group photo" | **No text exists anywhere.** OCR returns an empty string, so there is nothing to embed and nothing to match. This query cannot work through the text pipeline at any quality — it needs the image itself to be searchable. Three corpus files are already invisible for exactly this reason. |

Layer two keeps its own case: **"what did HR say during the internship interview"** — an
answer about content, with citations, only after the user asks a question rather than
searches for a thing.

**Query 7 is the one that breaks the architecture rather than stressing it.** Queries 1–6
are hard because the description has to be understood. Query 7 is hard because the pipeline
has no representation of the document at all: a photo of people has no text, so OCR yields
nothing, so no chunk exists, so no vector exists. It is not ranked badly — it is absent.
Fixing it requires embedding the *image*, which is a second modality, not a better filter.

**The insight these encode:** most personal-document queries are *metadata and identity
queries wearing semantic clothing*. Retrieval must understand the description and filter
first, then search semantically inside what is left. A pipeline that goes straight to
vector similarity fails 1, 2, 3 and 5 while looking excellent on generic content
questions.

---

## The refusal rule

**Refusal is about absence from the corpus. It is never about the sensitivity of the
topic.**

- Returning the user's own stored Aadhaar card is **success**. It is their document, in
  their account, and finding it is the entire point of the product.
- Producing an Aadhaar number, a passport number, or a bank account number that was
  never stored is **failure**, whether it comes from model knowledge or from a guess.

A `must_refuse` gold row therefore describes a document that genuinely is not in the
corpus. It never describes a document that is present but sensitive. Encoding the
sensitivity version instead looks correct in review and fails on stage the first time
someone searches for their own ID.

---

## Retrieval contract

Every query goes through two stages.

**Stage 1 — Query understanding.** One LLM call converts the natural-language
description into:

```json
{
  "filters": {
    "document_type": "aadhaar | pan | marksheet | receipt | letter | null",
    "sender": "professor | <name> | null",
    "source_type": ["email", "pdf", "image", "audio", "note", "calendar"],
    "date_range": { "from": "...", "to": "..." },
    "has_attachment": true,
    "entities": ["..."]
  },
  "semantic_query": "the part that actually needs meaning-based search",
  "needs_time_resolution": "last semester"
}
```

If `needs_time_resolution` is set, resolve the phrase against calendar events and email
threads **before** retrieving.

**Stage 2 — Filtered hybrid retrieval, ranked by document.** Apply filters, then dense +
BM25 with RRF fusion inside the filtered set. Chunk scores aggregate up to a **document**
score. Two chunks from one PDF are one result, not two. Return ranked documents, each
carrying its best-matching chunk as evidence.

**Never skip stage 1.** It is the difference between this project and a search box.

---

## Architectural rules

These are properties of the product, not implementation preferences. A future change
that violates one of them is a regression even if every test passes.

**1. No document content in any prompt, at layer one.**

The boundary is **what goes into the prompt**, never what the call is for. A step cannot
be justified by claiming it improves search; only by what it sends.

**Permitted at layer one:** a model call whose entire input is the user's own query text.
The user typed those words, deliberately, knowing they are being used to search. Sending
"the mail yash sent to rutuja" is categorically different from sending that mail.

**Forbidden at layer one:** any prompt containing retrieved chunk text, document content,
titles, filenames, snippets, extracted metadata, or search results — whole or
summarised, before ranking or after it. "Summarise the results", "rerank these snippets"
and "pick the best of these documents" are all forbidden, however much they might improve
the ranking.

This is a privacy property, not a performance optimisation. It is what allows someone to
find their Aadhaar card without any part of that card entering a third party's prompt.
Query understanding (stage 1) sits inside the permitted half: it reads the question and
returns filters, and never sees a document.

Enforced structurally in `tests/test_no_llm_in_layer_one.py`: layer one must not import
the generation module, and the query-understanding prompt builder must accept a query
string and nothing else. A behaviour test would keep passing until the day someone adds
the forbidden step.

**2. Identifiers are masked before anything leaves the machine.** OCR of an identity
document produces the identity number as plain text, and that text is then embedded —
today via a hosted API. Aadhaar (12 digits) and PAN (`ABCDE1234F`) patterns are masked
before embedding. The document stays findable by type, issuer, date and context; the
number itself never leaves local storage.

**Scope is Aadhaar and PAN, deliberately.** Phone numbers, addresses and account
numbers are *not* masked. Both have weaker formats: an Indian mobile is `[6-9]\d{9}`,
which also matches order numbers and reference IDs, and masking one of those silently
destroys retrievable text that nobody notices until a search fails. Aadhaar carries a
Verhoeff check digit and PAN has a distinctive shape, so both can be detected without
guessing.

State this as a scoped claim rather than a broad one. "Aadhaar and PAN are masked before
anything leaves the machine; other personal data is out of scope because the
false-positive cost exceeds the leak it would prevent" is defensible. "Everything is
masked" is not, and is the kind of claim that collapses under one question.

**Built and enforced.** `MaskedText` is the only type the embedder accepts, and it is
verified on content rather than provenance - so a forged one carrying an identifier is
rejected however it was constructed. Masking runs before storage as well as before the
request, since a number sitting in the database has not stayed on the machine either.

---

## What "working" means

**Layer one**

- The correct file is at **rank 1**.
- Results show thumbnails, so the user recognises the document by looking at it.
- The file opens in-app: page through a PDF, zoom an image.
- The file downloads.
- When the document is not in the corpus, the system says so and offers nothing.

**Layer two**

- Every answer cites specific source documents. Clicking a citation opens the source with
  the exact span highlighted.
- When retrieval is weak, the system says it doesn't have that. It never fills gaps from
  model knowledge.

**Both**

- Documents organize themselves. The user files nothing: type, entities, dates and
  timeline are extracted on ingest.
- A user can only ever retrieve their own documents. Enforced at the database, not just
  in application code.
- Deleting the account removes rows, vectors, and files — and this is demonstrable.

---

## How it is measured

| metric | scope | role |
|---|---|---|
| **Recall@1** | layer one | **Primary.** Was the right file first? |
| **MRR@10** | layer one | Secondary. How far down was it when it wasn't first? |
| **Refusal accuracy** | layer one | Did absent documents get refused rather than substituted? |
| Answer faithfulness | layer two | Secondary. Judged, therefore less reliable — never the headline number. |

Recall@1 is a hard number. Either the Aadhaar card came back first or it did not. That
is the metric to report and defend, and it is the reason document retrieval is a better
framing for this project than chat: it replaces a judged score with a counted one.

---

## Two core requirements that are not yet built

Both are **core**, not future work. Each makes a sentence in this document true or false.

### 1. Files are discovered on the device, not uploaded

The product sentence is *"it searches the files already on your phone."* Today the system
searches **files you have uploaded to it**, which is a different and much weaker product —
it asks the user to gather the documents first, and gathering is the problem being solved.

**A PWA cannot do this, and no amount of engineering changes that.** Browsers sandbox
storage deliberately: there is no web API that enumerates a phone's Downloads folder or
gallery, watches for new files, or indexes in the background. The File System Access API
covers user-picked handles on desktop, not device-wide scanning, and is not the same thing.
This is a platform boundary, not a missing feature.

**Therefore Capacitor moves from optional stretch to required.** A native shell gets
`READ_MEDIA_*` permissions, filesystem enumeration, and background execution. Without it,
"already on your phone" is not a claim this project can make.

`PORTABILITY.md`'s discipline pays for itself exactly here: business logic already lives in
`apps/api` and `packages/core`, and platform capabilities already sit behind interfaces, so
the shell change is an implementation of existing interfaces rather than a rewrite. That was
the point of the constraint.

### 2. Visual search, because some documents have no text

Hero query 7 has no text-pipeline path at any quality (see above). Three corpus files are
already unfindable by any query for this reason, and that is recorded as a limitation in
every measurement report so far.

It also matters for the flagship. **`document_identity` has no working path today**:
Tesseract reads zero words off a laminated college ID card, measured, not assumed. Visual
search gives that query a second route that does not depend on OCR succeeding on a
reflective plastic surface.

The requirement is that a text query can match a document by **what it looks like**. See
`prompts/clip-image-embeddings.md` for how.

---

## What this is NOT

- Not a note-taking app. Memora doesn't ask users to write anything.
- Not an always-on screen recorder. Capture is deliberate and consented.
- Not a general chatbot. If the document isn't in the user's corpus, the correct response
  is "I don't have that."
- Not a document QA tool. Upload-only would make this NotebookLM. **At least one
  automatic, non-upload intake path is required** — the problem being solved is that
  documents are already scattered, so requiring manual gathering sidesteps the problem
  rather than fixing it.

  This line used to name the Gmail connector specifically, and Gmail sat under "never
  cut". **Device indexing now satisfies it, and satisfies it better.** The rule was never
  about Gmail; it was about the product not asking the user to do the gathering. Judged
  against that:

  - Gmail covers **one** source. A device scan covers everything that ever landed on the
    phone — email attachments among them, since they get saved to `Downloads/`.
  - Gmail is a hosted third party, an OAuth flow stuck in Testing mode, and a consent
    screen. Device indexing reads local files and sends nothing anywhere, which is the
    same direction as every other architectural decision here.
  - The product sentence is *"searches the files already on your phone."* A device scan
    **is** that sentence. Gmail is adjacent to it.

  So this is a substitution that makes the requirement stronger, not an exemption from
  it. **Gmail becomes documented future work** — worth building, no longer load-bearing.
  If device indexing is not built either, the rule is violated and upload-only is what
  ships, which is the outcome the line exists to prevent.

---

## Honest novelty claims

Do **not** claim novelty on: RAG over personal data, citations, multimodal ingestion,
hybrid vector+relational storage, OCR. All of these shipped in products before 2026.

Defensible claims:

1. **Description-to-document retrieval for personal archives** — resolving how a person
   remembers a document ("my Aadhaar card," "a professor sent it," "last semester") into
   retrieval constraints over their own files. Measured by Recall@1, which has no good
   public benchmark for this task. That gap is the opportunity.
2. **Privacy-first by construction** — per-owner isolation enforced in the database,
   layer-one retrieval that never sends a document to a model, and identifier masking
   before embedding. "The Aadhaar number never leaves the device" is a claim an examiner
   can watch being demonstrated.

   **State this in three layers, and do not collapse them.** The claim is strong because it
   is precise, and it gets weaker the moment it is rounded up to "nothing leaves the
   device".

   1. **Documents never leave.** Enforced architecturally by rule 1, tested by
      `test_no_llm_in_layer_one.py`. This is the strong claim and it holds.
   2. **The query does leave.** Stage 1 sends the user's own words to a hosted model, and
      the query is the personal part — *"the mail yash sent to rutuja"* names a person and
      a relationship; *"my college fee receipt"* names a document the user holds. On
      Google's **free tier**, the terms permit human reviewers to read API input and use it
      to improve products. On the **paid tier** they forbid both. So the honest form is
      "queries leave under terms that forbid review and training", and it is only true if
      the paid tier is actually taken. See `prompts/quota-ceiling-decision.md`.
   3. **Fully-local stage 1 is future work, with a measured obstacle.** Running the
      extractor on-device would stop the query leaving at all. `PHASE3.md` records why that
      is not free: a weaker extractor (`gemini-flash-lite-latest`) scored Recall@1 0.789,
      *below* the 0.842 achieved by using no extractor at all. A wrong filter is worse than
      no filter, so a small local model is a real risk, not an obvious win.

   Claiming layer 1 alone is accurate. Claiming layers 1–2 requires paying. Claiming layer 3
   is claiming something not built.
3. **Self-organizing archive** — document type, timeline and entity graph built without
   the user filing anything.

Claims 1 and 2 can both be demonstrated on stage in under a minute. Lead with them.

---

## Non-negotiable scope

**OCR is phase-1 critical, not a later enhancement.** Most target documents are photos
and screenshots with no text layer, so without OCR the flagship query returns nothing.
`mail.pdf` already in the test corpus is exactly this case: four pages, zero extractable
text. The roadmap has not yet been resequenced for this.

If the schedule slips, cut in this order: reranking → query transformation → extra
connectors → entity resolution.

**"native app" used to be at the end of that list and has been removed from it.** It was
the right thing to cut when the product was "upload your documents and search them". It is
not cuttable now that the product is "search the files already on your phone", because a
PWA cannot enumerate device storage at all. Cutting it does not degrade the product; it
changes which product this is.

Never cut: **OCR**, Gmail connector, query understanding, ranked file results with viewer
and download, per-owner isolation, the evaluation harness.

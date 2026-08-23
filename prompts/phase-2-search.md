# Phase 2 — /search, ranked documents

**Status: plan only. Nothing implemented pending approval.**

## Goal

Describe a document, get the document back, ranked, with no generation call anywhere in
the path.

## What I read

- `docs/PRODUCT.md` — two layers, architectural rule 1 (layer one runs without an LLM),
  Recall@1 as the primary metric
- `docs/ROADMAP.md` — phase 2 and the parallel frontend track that consumes this contract
- `apps/api/src/memora/repositories/chunk.py` — `search_dense` returns chunks, flat
- `apps/api/src/memora/db/models/{memory,chunk}.py` — **no file bytes, no path, no page**
- `apps/api/src/memora/api/routers/uploads.py` — reads bytes, chunks them, discards them
- `apps/api/src/memora/services/retrieval.py` — `MIN_SIMILARITY_UNCALIBRATED`, measured
  wrong and still unset
- `apps/api/src/memora/eval/retrieval.py` — the harness that will compute the metrics

## Assumptions

**1. File storage is a prerequisite, and it does not exist.** This is the one that
changes the shape of the phase. `/uploads` reads the bytes, extracts text, and throws the
bytes away. `Memory` has `filename` but no path and no blob.

So thumbnails, the in-app viewer and download — the three things `PRODUCT.md` says make
an answer an answer — are all currently impossible. A `/search` response containing a
`thumbnail_url` would be pointing at nothing.

Proposal: content-addressed local storage. `data/blobs/<user_id>/<sha256>` with the path
recorded on `Memory`, deduplicating identical uploads for free. **The stored path is
derived from the hash, never from the uploaded filename** — the filename stays data, as
the existing comment in `uploads.py` already promises. Gitignored, same as the corpus.

Without this, phase 2 delivers a ranked list of names with no way to look at anything.
**This is the assumption most worth overruling if you would rather split it out.**

**2. Document score is the best chunk's score.** For finding a document, one strong match
identifies it; averaging dilutes a short decisive match with a long irrelevant document.
Named constant, and a knob the baseline will test rather than a truth.

**3. Over-fetch chunks and group in the repository, rather than `DISTINCT ON`.**
`DISTINCT ON (memory_id)` reads every chunk and defeats the HNSW index. Fetching
`limit * FANOUT` chunks by vector distance uses the index and groups cheaply.

The tradeoff is real: a document whose only matching chunk falls outside the fetch window
is invisible, and that risk grows with corpus size. At 10 documents it cannot bite; at
10,000 it can. Worth naming so the baseline can measure it rather than discovering it.

**4. POST, not GET.** "find my Aadhaar card" is personal, and a GET puts it in the URL,
the browser history, and every access log in between. `CLAUDE.md` forbids personal data
in query strings.

**5. Recall@1 and MRR do not go in the response.** You offered either; this is the "state
how" branch, and I think it is clearly right. Those are properties of a *run over the
gold set*, not of a single query — one search has no Recall@1, because recall is a
fraction over many queries with known answers. Putting them in the API response would
mean either shipping a number that is always 0 or 1, or teaching the production endpoint
about the gold set. The harness computes them; the response carries `rank` and `score`,
which is what the harness needs.

**6. Refusal is an empty result list plus a flag.** Same
`MIN_SIMILARITY_UNCALIBRATED` constant, new meaning: "is the top document good enough to
show". Measured evidence says it never fires today, so refusal at layer one will be
inert until phase 3 calibrates it. That stays visible rather than being papered over with
another guess.

**7. Chunks do not know their page.** For a PDF, click-through can only open page 1.
Adding a nullable `page` column and populating it during extraction is a small migration
and makes the viewer land on the match. Flagged as a decision, not assumed.

## Files that will change

**Create**
```
apps/api/src/memora/services/storage.py        content-addressed blob store
apps/api/src/memora/services/search.py         chunk results -> ranked documents
apps/api/src/memora/api/routers/search.py      POST /search
apps/api/src/memora/api/routers/files.py       GET thumbnail + file
apps/api/migrations/versions/0002_blob_and_page.py
apps/api/tests/test_search.py
apps/api/tests/test_storage.py
apps/api/tests/test_no_llm_in_layer_one.py
```

**Modify**
```
apps/api/src/memora/db/models/memory.py    + blob_path, byte_size, content_hash
apps/api/src/memora/db/models/chunk.py     + page (nullable)
apps/api/src/memora/repositories/chunk.py  search_dense gains a fan-out
apps/api/src/memora/api/routers/uploads.py persist bytes, generate a thumbnail
apps/api/src/memora/config.py              + blob_root, search fan-out, thumbnail size
.gitignore                                  data/blobs/
openapi.json, packages/core/src/types/api.ts
```

## Implementation requirements

**Contract.** The frontend track starts from this, so it is the part to get right.

```jsonc
POST /search   {"query": "find my aadhaar card", "limit": 10}

{
  "refused": false,
  "reason": null,                  // "no_evidence" | "weak_evidence" when refused
  "total": 3,
  "results": [
    {
      "rank": 1,
      "memory_id": "uuid",
      "title": "Aadhaar front",
      "filename": "IMG_20240817.jpg",   // as uploaded, display only
      "source_type": "image",           // image | pdf | email | audio | note | calendar
      "score": 0.71,
      "snippet": "GOVERNMENT OF INDIA ... [AADHAAR_NUMBER] ...",
      "matched_chunk_id": "uuid",
      "page": 2,                        // null for images
      "byte_size": 182344,
      "thumbnail_url": "/memories/{id}/thumbnail",
      "file_url": "/memories/{id}/file"
    }
  ]
}
```

`snippet` comes from the stored chunk, which is already masked — so a result card cannot
display an identifier even if the source document contains one.

**Ranking.** Embed the query (masked, like every other embedding), fetch
`limit * FANOUT` chunks by cosine distance, group by `memory_id`, score each document by
its best chunk, sort, take `limit`. Rank is 1-based and assigned server-side so the
harness and the UI agree.

**Storage.** `sha256` of the bytes; write once under `blob_root/<user_id>/<hash>`; record
path, hash and size on `Memory`. Re-uploading the same file reuses the blob.

**Thumbnails.** Generated at ingest, not on request: 320px longest edge, JPEG, beside the
blob. PDFs render page 1. `GET /memories/{id}/thumbnail` streams it, scoped through the
repository like everything else.

**No LLM, structurally.** `search.py` must not import `generation`. A test asserts the
import graph, not just the behaviour — behaviour tests pass right up until someone adds a
"summarise the results" step, and the whole point is that a later change cannot quietly
do that.

## Security requirements

- Both file endpoints go through `MemoryRepository.get`, so RLS and the repository scope
  both apply. A blob path is never trusted from a request.
- Blob paths are derived from a content hash. The uploaded filename is stored as data and
  never joined onto a path.
- `Content-Disposition: attachment` with a sanitised filename, and an explicit
  `Content-Type` — an uploaded HTML file must not render in the origin.
- The query is masked before embedding, as now.
- Search queries are never logged at full text: personal descriptions are personal.

## Acceptance criteria

1. `POST /search` returns documents, not chunks. Two matching chunks from one PDF produce
   one result.
2. Results carry rank, score, snippet, source type, thumbnail and file URLs.
3. `GET /memories/{id}/file` returns the exact bytes uploaded, and 404s for another
   user's memory.
4. `GET /memories/{id}/thumbnail` returns an image for both a PDF and an image upload.
5. Re-uploading an identical file creates no second blob.
6. A test fails if `search.py` imports the generation module.
7. Below the similarity floor, results are empty and `refused` is true.
8. Snippets from a document containing an identifier show the mask token, never digits.

## How the harness computes the metrics

Not in the response — in `memora.eval.retrieval`, over the whole gold set:

```
for each gold row:
    results = POST /search {query}
    rank    = 1-based position of the first result whose filename is in
              expected_sources, else None

Recall@1 = rows with rank == 1                    / rows with expected_sources
Recall@5 = rows with rank <= 5                    / rows with expected_sources
MRR@10   = mean(1/rank, or 0 when rank is None)   over the same rows
Refusal  = must_refuse rows where refused is true / must_refuse rows
```

`must_refuse` rows are scored only on refusal and excluded from the recall
denominators — a row with no expected file cannot contribute to a recall fraction.

## Checks to run

```
cd apps/api && uv run pytest && uv run ruff check .
cd apps/api && uv run alembic upgrade head
pnpm gen:types && pnpm -C packages/core typecheck
```

## How to verify

1. `docker compose up -d`, migrate, run the API.
2. Upload the corpus, then search for something in the TCS screenshot:

```
curl -X POST http://localhost:8000/search -H "Content-Type: application/json" \
  -d '{"query":"the AI engineer job someone shared"}'
```

Expect the WhatsApp screenshot at rank 1, with a snippet from the posting.

3. Open the returned `file_url` and confirm the bytes match the original.
4. Confirm no generation call occurred — the API log shows no model request for a search.

## Risks

**This phase is two features.** Storage plus ranked search. If it needs splitting, ship
storage first: search without it returns a list of filenames nobody can open, which is
not the product.

**The similarity floor is still uncalibrated,** so criterion 7 will only be provable once
phase 3 sets a real value. Until then the refusal branch exists but never fires, which
should be stated in the phase-2 report rather than discovered in phase 3.

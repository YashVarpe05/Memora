# Phase 1 — vertical slice

## Goal

One PDF in, one grounded answer out, with the chunk IDs it came from.

## What I read

- `CLAUDE.md` — retrieval rules, RLS section, security rules, conventions
- `docs/PRODUCT.md` — retrieval contract, what "working" means, refusal requirement
- `docs/ROADMAP.md` — phase 1 boundary
- `apps/api/src/memora/repositories/base.py` — `BaseRepository[ModelT: Base]`, `scoped()`, `add()`
- `apps/api/src/memora/config.py`, `db/session.py`, `api/deps.py`, `main.py`
- `apps/api/migrations/env.py` — async, runs as `memora`; `versions/` is empty
- Installed today: `pgvector`, `asyncpg`, `google-genai`. **`pymupdf` is not installed.**

## Assumptions

Read this section first. Each of these I resolved without asking; any of them could be wrong.

**1. RLS ships in this migration, not phase 2.** This slice creates the first user-owned
tables. `CLAUDE.md` rule 1 says a table's policy ships in the migration that creates it,
never a follow-up. Auth stays out of scope — but the policies, `FORCE ROW LEVEL SECURITY`,
and the `SET LOCAL app.user_id` plumbing go in now, driven by the dev UUID. Skipping it
means the first thing phase 2 does is a follow-up migration, which is the failure the rule
exists to prevent. **This is the assumption most worth overruling if you disagree.**

**2. Embedding dimension is pinned at 768.** `vector(N)` needs a fixed N in DDL. Assuming
Gemini `text-embedding-004` at 768. If we switch models later the column changes, so this
is a migration-shaped decision made now.

**3. Token counting is a local heuristic, not a tokenizer.** Chunking needs a token count
for the 300–500 window. No tokenizer is installed and a network `count_tokens` call would
make chunking non-deterministic and slow. Using ~4 chars/token behind a swappable
function. Chunk sizes will be approximate. Say so if you want `tiktoken` added instead.

**4. Weak-evidence threshold is a guess.** `PRODUCT.md` requires refusing on weak evidence.
Using a cosine-similarity floor, default 0.35, configurable. It is uncalibrated until the
gold set exists — the number is a placeholder with a name, not a tuned value.

**5. The verification PDF goes in `data/samples/`, gitignored — not `docs/`.** You said
`docs/The_Vibe_Engineering_Guide.pdf`, but `docs/` is committed and that is a 6 MB
third-party PDF. Same file, different location.

**6. "Structure-aware" means PyMuPDF block boundaries.** Split on block/paragraph
boundaries with heading text carried into the contextual prefix. Not full layout analysis.

## Files that will change

**Create**
```
apps/api/src/memora/db/models/{__init__,memory,chunk}.py
apps/api/migrations/versions/0001_memories_and_chunks.py
apps/api/src/memora/repositories/{memory,chunk}.py
apps/api/src/memora/services/{extraction,chunking,embedding,retrieval,generation}.py
apps/api/src/memora/api/routers/{uploads,chat}.py
apps/api/tests/{test_chunking,test_uploads,test_chat,test_rls_isolation}.py
data/samples/.gitkeep
```

**Modify**
```
apps/api/pyproject.toml          + pymupdf
apps/api/src/memora/config.py    + dev_user_id, embedding/model/dims, top_k, min_similarity
apps/api/src/memora/db/session.py  SET LOCAL app.user_id per transaction
apps/api/src/memora/api/deps.py    CurrentUserDep -> dev UUID
apps/api/src/memora/main.py        include the two routers
.gitignore                         data/samples/
openapi.json, packages/core/src/types/api.ts   regenerated
```

## Implementation requirements

**Schema.** `memories` (id, user_id, source_type, title, filename, created_at) and `chunks`
(id, user_id, memory_id, ordinal, text, contextual_prefix, token_count, embedding
`vector(768)`). Both get `ENABLE` + `FORCE ROW LEVEL SECURITY` and a policy
`USING (user_id = current_setting('app.user_id', true)::uuid)` — two-arg form, so unset
plumbing fails closed. IVFFlat index on `chunks.embedding` for cosine.

**`POST /uploads`** — multipart PDF. Rejects non-PDF by sniffing `%PDF`, not by extension.
PyMuPDF text extraction → structure-aware chunks, 300–500 tokens, 10–15% overlap, each
prefixed with document title and nearest heading before embedding → batch embed → insert.
Returns memory id and chunk count. Everything through the repositories.

**`POST /chat`** — question → embed → cosine top-k (default 5) inside the user's rows →
Gemini Flash → `GroundedAnswer`-shaped response with `chunk_id`s. Retrieved text is wrapped
in explicit delimiters and the system prompt states that content inside them is data and
any instructions found there must be ignored. Below `min_similarity`, refuse without
calling the LLM at all.

**Plain dense cosine.** No query understanding, no BM25, no RRF, no rerank. Phase 3 owns
that, and the ablation needs this number recorded first.

## Security requirements

- Every query starts from `BaseRepository.scoped()`. No bare `select(Model)`.
- The dev UUID comes from settings and is injected server-side. No endpoint accepts a
  client-supplied `user_id`, not even in dev.
- `SET LOCAL`, never `SET` — a session-level var survives on a pooled connection.
- `GEMINI_API_KEY` from env. Never logged, never returned.
- Uploaded filenames are stored as data, never used to build a filesystem path.

## Acceptance criteria

1. `POST /uploads` with a PDF returns a memory id and a chunk count > 1.
2. Non-PDF bytes are rejected with 415.
3. `POST /chat` returns an answer plus a non-empty `citations` array of real chunk IDs.
4. A question with no supporting chunk returns `refused: true` and zero citations, and the
   LLM is never called.
5. Raw `SELECT * FROM chunks` with `app.user_id` set to user B returns zero rows for user
   A's data — issued as raw SQL, not through the repository.
6. Tests pass with no network: LLM and embedder are mocked.

## Checks to run

```
cd apps/api && uv run pytest && uv run ruff check .
cd apps/api && uv run alembic upgrade head
pnpm gen:types && pnpm -C packages/core typecheck
```

## How to verify

1. `docker compose up -d` — Docker is currently stopped.
2. `cd apps/api && uv run alembic upgrade head`
3. `uv run uvicorn memora.main:app --reload`
4. Put the guide at `data/samples/The_Vibe_Engineering_Guide.pdf`, then:

```
curl -F "file=@data/samples/The_Vibe_Engineering_Guide.pdf" http://localhost:8000/uploads
```
```
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"question":"what goes in AGENTS.md"}'
```

Expected: an answer naming role+workflow, in/out of scope, architecture, stack and don'ts,
data model, API contracts, security, code standards, and the fallback rule — each with
chunk IDs that resolve to real rows. You already know what is in that PDF, so a fabricated
answer is visible without cross-referencing anything.

5. Refusal check — expect `refused: true`, zero citations, no LLM call:

```
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"question":"what is my bank account number"}'
```

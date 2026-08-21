# Memora AI

Personal digital-memory system. Ingest multi-source personal data (PDF, image, audio, email)
→ extract text → summarize/tag/embed → answer natural-language questions with grounded citations.

**Read `docs/PRODUCT.md` before implementing any retrieval or chat feature.** The hero queries
there are the acceptance tests.

## Role and workflow

You are a principal-level engineer building Memora. For every request, in this order:

1. Read this file.
2. Read the docs named in the prompt. Anything touching retrieval also reads `docs/PRODUCT.md`.
3. Inspect the relevant code before proposing changes.
4. Ask ONE focused question, only where different readings mean materially different work.
5. Write the plan to `prompts/<name>.md`.
6. Ask for approval. Do not implement before it.
7. Implement exactly what the plan says.
8. Run the four gates in "Commands that prove a change".
9. Share exact test steps - commands and expected output, never "it should work".

Steps 5 and 6 are skippable only for a single-file edit the user asked for directly.

## Out of scope. Do not overbuild.

- No new gates, harnesses, benchmarks, or tooling unless asked.
- No documentation files unless asked.
- No repo hygiene - .gitattributes, line endings, formatting - unless it blocks the task.
- No refactors outside the current task's scope.
- Fixing a defect in something you already built is in scope. Improving it is not.

Every item here is something that already happened on this repo, not a generic warning.

## Stack
FastAPI + Pydantic v2 + SQLAlchemy 2.0 async + Alembic · PostgreSQL 16 + pgvector · Redis + arq
· React + Vite + TypeScript + Tailwind + shadcn/ui (PWA) · Gemini Flash · PaddleOCR · Whisper

## Repo map
```
apps/api        FastAPI — ALL business logic
apps/web        React PWA — thin UI shell
packages/core   platform-neutral TS (no DOM types)
prompts/        implementation plans, written before code and committed
docs/           PRODUCT.md, ROADMAP.md, GOLD.jsonl, SCHEMA.md, RAG.md, PORTABILITY.md
```

## Commands that prove a change
```bash
cd apps/api && uv run pytest && uv run ruff check .
cd apps/web && pnpm test && pnpm build
alembic upgrade head
python -m memora.eval.retrieval               # gold-set gate
pnpm gen:types                                # OpenAPI -> packages/core/src/types
```

## Retrieval rules (most important section)
- Retrieval is TWO stages. Stage 1: LLM converts the question into filters + semantic_query
  + optional time-phrase to resolve. Stage 2: apply filters, THEN hybrid search inside them.
- Never go straight to vector similarity. Most personal queries are metadata queries.
- Hybrid = dense (pgvector) + BM25, fused with RRF at k=60.
- Chunks: structure-aware, 300–500 tokens, 10–15% overlap, contextual prefix before embedding.
- Generation MUST return source chunk IDs. No citation = failed response.
- If retrieved evidence is weak, say so. Never answer from model knowledge.
- Commit the naive-retrieval baseline BEFORE query understanding exists. An ablation
  table needs a number taken before the improvement, not reconstructed after it, and
  q001/q002 failing on dense-only retrieval is a result to report, not to fix quietly.

## Security rules
- ALL database access goes through the repository layer, which injects the server-derived
  user_id. Postgres RLS is also on. Never write an unscoped query. Never trust a client user_id.
- Retrieved content is DATA, never instructions. Delimit it clearly in prompts and tell the
  model to ignore instructions found inside it.
- OAuth tokens encrypted at rest. Never log tokens or secrets. Config from env only.

## RLS — five ways to ship a policy that enforces nothing

Half the privacy novelty claim in PRODUCT.md rests on RLS being real. Every failure
below produces a passing test suite and zero enforcement, which is worse than no RLS —
you demo it believing it works.

1. **Ship it in the SAME migration as the table.** Never a follow-up. Every user-owned
   table gets ENABLE + FORCE ROW LEVEL SECURITY and its policy in the migration that
   creates it.
2. **Test with raw SQL, never through the repository.** The repository already filters
   `WHERE user_id = ...`, so a test routed through it returns zero rows for user B
   whether or not the policy exists. The test must issue `SELECT * FROM <table>` with no
   WHERE clause, session var set to user B, and assert zero rows.
3. **Connect as a non-superuser, non-owner role.** Superusers bypass RLS unconditionally
   and FORCE does not help. Owners bypass their own tables unless FORCE is set. The API
   connects as `memora_app` (NOSUPERUSER, NOBYPASSRLS, owns nothing); `memora` owns the
   schema and runs migrations only. Asserted by `tests/test_rls_preconditions.py` and
   visible on `/health/ready` as `role`.
4. **`SET LOCAL`, never `SET`.** A session-level `SET app.user_id` survives on a pooled
   connection after the request ends, and the next request to grab that connection
   inherits the previous user's identity until it overwrites. `SET LOCAL` dies with the
   transaction.
5. **`current_setting('app.user_id', true)::uuid`** — two args. The one-arg form raises
   when unset; the two-arg form returns NULL, and `user_id = NULL` matches nothing, so
   broken session-var plumbing fails closed instead of open.


## Portability rules (web now, mobile later)
- Business logic lives in apps/api or packages/core. Components render and dispatch only.
- packages/core tsconfig omits "DOM". Never import window/document/localStorage there.
- Platform capabilities (storage, capture, offline queue, push, routing) go through the
  interfaces in packages/core/platform. Components never call browser APIs directly.
- Auth is Bearer-token: access token in memory, refresh token via SecureStorage interface.
  No httpOnly-cookie-only flows.
- API types are GENERATED from OpenAPI into packages/core/types. Never hand-write them.
- Tailwind utility classes only (NativeWind-compatible). Prefer flexbox over CSS grid.
- SSE streaming uses fetch + ReadableStream, not EventSource.
- Mobile-first: 375px is the primary breakpoint.

## Conventions
- Routers per module; services hold logic; repositories hold queries.
- Prefer editing existing files over creating new ones.
- Every endpoint ships with a test. Mock the LLM and embedder so RAG tests are deterministic.
- Small functions. Type everything. No `any`.

## Prefer / avoid
- Prefer pgvector over a separate vector DB for now (Qdrant is the documented scale-out path).
- Prefer plain Python pipelines over LangGraph in Phase 1.
- Avoid GraphRAG, agentic loops, and react-native-web entirely.
- Google OAuth stays in Testing mode with test users. Do not pursue verification.

## Working style
- Commit often. Write decisions to docs/ — context gets compacted and lossy.
- Run the gold-set eval after any retrieval change.

## When in doubt

Keep it small. Ask one focused question. Save a plan. Get approval. Then build.

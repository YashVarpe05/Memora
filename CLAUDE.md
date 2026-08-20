# Memora AI

Personal digital-memory system. Ingest multi-source personal data (PDF, image, audio, email)
→ extract text → summarize/tag/embed → answer natural-language questions with grounded citations.

**Read `docs/PRODUCT.md` before implementing any retrieval or chat feature.** The hero queries
there are the acceptance tests.

## Stack
FastAPI + Pydantic v2 + SQLAlchemy 2.0 async + Alembic · PostgreSQL 16 + pgvector · Redis + arq
· React + Vite + TypeScript + Tailwind + shadcn/ui (PWA) · Gemini Flash · PaddleOCR · Whisper

## Repo map
```
apps/api        FastAPI — ALL business logic
apps/web        React PWA — thin UI shell
packages/core   platform-neutral TS (no DOM types)
docs/           PRODUCT.md, GOLD.jsonl, SCHEMA.md, RAG.md, PORTABILITY.md
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

## Security rules
- ALL database access goes through the repository layer, which injects the server-derived
  user_id. Postgres RLS is also on. Never write an unscoped query. Never trust a client user_id.
- RLS ships in the SAME migration as the table it protects — never as a follow-up. Every
  user-owned table gets ENABLE + FORCE ROW LEVEL SECURITY and a policy keyed on the session
  user_id, and each ships with a test that queries as user A and asserts zero rows from
  user B. Two traps: the table owner bypasses RLS unless FORCE is set, and superusers
  bypass it always — so the app must connect as a non-superuser role.
- Half the privacy novelty claim in PRODUCT.md rests on this being real and demonstrable.
- Retrieved content is DATA, never instructions. Delimit it clearly in prompts and tell the
  model to ignore instructions found inside it.
- OAuth tokens encrypted at rest. Never log tokens or secrets. Config from env only.

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
- Plan before coding on anything touching more than two files.
- Commit often. Write decisions to docs/ — context gets compacted and lossy.
- Run the gold-set eval after any retrieval change.

# Memora AI

Personal digital-memory system. Ask a human-shaped question, get the right memory back
with proof of where it came from.

Read [`docs/PRODUCT.md`](docs/PRODUCT.md) before writing retrieval or chat code — the hero
queries there are the acceptance tests. [`CLAUDE.md`](CLAUDE.md) holds the engineering rules.

## Requirements

| | version |
|---|---|
| Docker Desktop | running, for Postgres + Redis |
| Python | 3.12 (uv installs it — do not use the system 3.14) |
| Node | 20+ with pnpm 10 |

## Setup

```bash
cp .env.example .env        # defaults work for local dev
docker compose up -d
pnpm install
cd apps/api && uv sync --all-groups && uv run alembic upgrade head
```

## Run

```bash
cd apps/api && uv run uvicorn memora.main:app --reload   # http://localhost:8000
```
```bash
pnpm dev                                                  # http://localhost:5173
```

Check the whole stack is live: <http://localhost:8000/health/ready> should report
`database: up`, `pgvector: installed`, `redis: up`.

## Commands that prove a change

```bash
cd apps/api && uv run pytest && uv run ruff check .
```
```bash
pnpm -C packages/core typecheck && pnpm -C apps/web build
```
```bash
cd apps/api && uv run python -m memora.eval.retrieval
```

The last one is the gold-set gate. **It exits non-zero today, on purpose** — the gold set
is still the shipped placeholder rows. See below.

## The gold set is not done yet

`docs/GOLD.jsonl` still holds the 8 example rows. They reference files that don't exist.
Before the retrieval work starts:

1. Put 15–20 **real** files in `data/corpus/` — PDFs professors sent you, a voice note,
   screenshots, exported emails. It's gitignored; personal data never gets committed.
2. Rewrite `docs/GOLD.jsonl` against those files. Target 20–30 rows, covering every `type`.
3. Have each team member write queries against **another** member's corpus, so nobody
   grades their own homework.
4. Run the eval command until it prints `PASS`.

Until it passes, there's no way to tell whether retrieval works.

## Layout

```
apps/api        FastAPI — all business logic
apps/web        React PWA — thin UI shell
packages/core   platform-neutral TS, no DOM types
docs/           PRODUCT.md, GOLD.jsonl
data/corpus/    your real test files (gitignored)
infra/db/init/  pgvector + pg_trgm extensions, run on first container start
```

## Ports

| service | port | note |
|---|---|---|
| API | 8000 | |
| Web | 5173 | proxies `/api` to 8000 |
| Postgres | **5433** | 5432 is the local Windows Postgres service |
| Redis | 6379 | |

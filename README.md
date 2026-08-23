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

1. Put **15 real files** in `data/corpus/` — PDFs professors sent you, a voice note,
   screenshots, exported emails. It's gitignored; personal data never gets committed.
2. Rewrite `docs/GOLD.jsonl` against them. Work backwards: open each file and ask *if I'd
   forgotten this existed, how would I have asked for it?* That sentence is the query.
   15 files gives 20 rows with no invention required.
3. Cover all seven `type` values — the gate fails without `must_refuse` and `metadata_only`.
4. Run the eval command until it prints `PASS`.

This is a **solo, two-hour task**. It does not need your teammates.

Later, when the team next meets, each person adds their own corpus and writes queries
against someone *else's*. That's a credibility improvement to the eval set — the answer
when an examiner asks whether one person wrote both the test and the system. It is not a
prerequisite for any code, and treating it as one is what kept this blocked.

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

## OCR benchmark

Settles which OCR engine goes into phase 4, with a number rather than an opinion.

```bash
cd apps/api && uv sync --group bench
```
```bash
cd apps/api && uv run python -m memora.bench.ocr
```

Inputs go in `data/ocr-bench/` (gitignored - they are photos of your books and
whiteboards):

```
images/<category>/<name>.png     the image
refs/<category>/<name>.txt       what it actually says
```

Categories are `printed`, `book_photo`, `screenshot`, `whiteboard`, `handwritten` -
20 images minimum, all five covered. Averaging handwriting together with printed text
hides the only finding that matters. Like the gold-set gate, this exits non-zero until
the inputs exist.

`gemini-flash` is metered and never runs unless you name it:
`--engines gemini-flash`.

**Parked.** Not on the critical path, and it needs 20 hand-written reference
transcripts. The gate stays red until someone picks it up.

**Known, measured 2026-08-22: PaddleOCR does not run on this machine, in either OS.**
paddlepaddle 3.3.1 installs cleanly and then dies at inference with
`ConvertPirAttribute2RuntimeAttribute ... oneDNN` — on Windows *and* inside the Linux
container. `FLAGS_use_mkldnn=0` does not help in either. An earlier note here said the
container was the fix; that was wrong, and testing it is what showed so.

So **tesseract is the only working engine**, and OCR quality is bounded by it. The
service reports this honestly: `available` lists engines that completed an inference,
`installed` lists engines that merely imported.

**Also measured: tesseract cannot read a laminated ID card.** `DSC02946.JPG`, a camera
photo of a college ID, yields zero words across all four rotations and page-segmentation
modes 3, 6 and 11 — twelve combinations, no text. That is a finding for the report, not a
reason to drop the `document_identity` gold row: a row that fails at baseline for a
stated reason is evidence.

## Two database roles

`memora_app` is what the API connects as: NOSUPERUSER, NOBYPASSRLS, owns nothing.
`memora` owns the schema and runs migrations. This split exists so RLS policies actually
bind — superusers bypass RLS unconditionally, and a table's owner bypasses it unless
FORCE is set. Point `DATABASE_URL` at `memora` and every policy silently stops enforcing.

`/health/ready` reports which role is connected. `tests/test_rls_preconditions.py`
fails the build if it can bypass.

## Ports

| service | port | note |
|---|---|---|
| API | 8000 | |
| Web | 5173 | proxies `/api` to 8000 |
| Postgres | **5433** | 5432 is the local Windows Postgres service |
| Redis | 6379 | |

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

**Correction, same day.** An earlier version of this section claimed tesseract cannot
read a laminated ID card. That was wrong: the file tested, `DSC02946.JPG`, turned out to
be a candid outdoor photo that happens to contain a lanyard, not a photograph *of* a
card. Twelve rotation and page-segmentation combinations returned no text, which is
expected for a photo with no text in it and says nothing about cards.

**No photograph of an ID card has been tested.** The claim will be worth making once one
is in the corpus, and not before.

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

## Device libraries and online processing

Each invitation now creates a separate device library. Existing development data remains
under the development identity; it is not silently copied into newly paired devices.
Device credentials persist in `data/auth/devices.sqlite3` (hashed). Keep that volume with
`data/blobs` and PostgreSQL when restarting or backing up a deployment.

Locally, start PostgreSQL/Redis, apply migrations, run the API and the durable worker:

```sh
docker compose up -d db redis ocr
cd apps/api
uv run alembic upgrade head
uv run uvicorn memora.main:app --host 127.0.0.1 --port 8000
# In a second terminal, from apps/api:
uv run python -m memora.worker
```

Run `pnpm dev` from the repository root. In the browser, connect to the local development
server, then open Index and choose a folder. On Android 11 or newer, connect with an HTTPS invitation,
read the online-processing disclosure, and grant file access. Discovery runs while the
app is open and when it resumes. It does **not** claim continuous Android background
execution. Uploaded jobs continue on the server even when the app closes. Browser folder
access depends on browser support and permissions; the folder-picker fallback requires a
new selection for each scan and does not infer removals across snapshots.

### Deploying when hosting is available

`compose.production.yml` packages the browser app, HTTPS gateway, API, worker, database,
and multilingual OCR. It requires a Linux host, a domain pointing to it, ports 80/443,
and an embedding-provider API key. No hosting account is created by this repository.
Set `MEMORA_DOMAIN`, `DB_PASSWORD`, `APP_DB_PASSWORD`, `OPERATOR_SECRET`, and
`GEMINI_API_KEY` in an untracked environment file. Generate strong independent hex secrets
(for example with `openssl rand -hex 32`); hex DB passwords avoid URL-encoding ambiguity.
Then run:

```sh
docker compose --env-file .env.production -f compose.production.yml up -d --build
```

The gateway provisions HTTPS. Only the gateway exposes public ports; production auth
has no loopback exemption. To create a five-minute, single-use invitation, an operator
calls `POST https://<domain>/api/pair/start` with the `X-Memora-Operator` header set to
`OPERATOR_SECRET`. Use the returned code and URL in the app (or render the response as a
QR). Each phone, tablet, and laptop browser needs its own invitation. Never put the
operator credential into a frontend build. Losing a device token requires a new library;
account recovery and cross-device sharing are not included.

Original documents are uploaded to the server. Aadhaar/PAN masking occurs before text
embeddings, not before original-file upload. Deleting a document removes its indexing
jobs so a worker cannot recreate it. Failed jobs show actionable errors and can retry
without resending the file. Password-protected PDFs and Word documents require an
unlocked copy; PDFs above 500 pages require splitting. Legacy DOC requires `antiword`,
which is included in the API container. OCR includes English, Hindi, and Marathi.


### Validation for the content-search implementation

Run `uv run pytest` from `apps/api` with PostgreSQL running and migrations applied.
The added synthetic acceptance cases cover random filenames, five Aadhaar query forms,
multilingual text, mixed scanned PDFs, encrypted PDFs, Word extraction, retries, device
isolation, duplicate locations, changed files, PDF page access, and embedding outages.
Run `pnpm typecheck`, `pnpm build`, and `pnpm gen:types` from the root.

A local Chromium smoke test exercised folder selection through the directory-input
fallback, durable indexing with real Tesseract OCR, search, and PDF page viewing/zoom at
375px, 768px, and 1366px widths. Its text/image embeddings were deterministic test doubles;
it is not a measurement of hosted-model retrieval accuracy. Real Tesseract with
`eng+hin+mar` correctly recognized three clean synthetic scanned documents (English and
Hindi Aadhaar headings, Marathi marksheet headings). This is a smoke test, not evidence
for arbitrary handwriting, blurred photos, or all document layouts.

The original gold-set gate remains blocked by the absent personal corpus. Do not report
new real-corpus Recall@1 or hosted search latency from these synthetic checks. Automatic
Android discovery still needs a physical-device check, and no online deployment has been
made without a hosting account.

Native packaging was attempted with `bash gradlew :app:assembleDebug --no-daemon` from
`apps/web/android`. Gradle reached project configuration but could not compile because
this machine has no Android SDK configured. Install/configure the SDK required by the
project (compile SDK 36), set `ANDROID_HOME` or `sdk.dir` in the ignored
`apps/web/android/local.properties`, then rerun that command. No verified APK or
physical-device result is claimed by the web smoke test.


Review verification (2026-11-06): the API suite passes 348 tests. Browser discovery
regressions (`pnpm --filter @memora/web test`) cover multiple saved roots, revoked
permissions, empty folders and incremental enumeration. Indic vowel signs are retained
in lexical matching; exact matches can select the relevant PDF page even when dense
retrieval prefers another page. Original-file and thumbnail responses disable caching.
The browser OCR/index/search/open trial passed again at phone, tablet and laptop widths
using synthetic scans and deterministic embedding doubles. This does not establish
production-model retrieval accuracy or physical Android compatibility. SDK license
installation was authorized, but the official SDK download encountered repeated network
resets; an APK has not been built or verified.

### Local web trial and repeatable validation

No hosting account is required for the local trial. Install Node 22+, pnpm, Python/uv,
Docker, and Tesseract with `eng`, `hin`, and `mar` language packs. Run `pnpm install`
and `uv sync --directory apps/api`, then `python scripts/web_trial.py` from the repo root.
Open **http://127.0.0.1:5175**, select **Connect to local development server**, then
choose a folder on Index. Keep the launcher running; Ctrl+C stops its app services.
Documents and pairing state persist locally. If language packs are in a custom folder,
set `TESSDATA_PREFIX` before launching. The launcher binds every app service to loopback.

This trial uses actual OCR, extraction, durable jobs, document labels and keyword search.
`EMBEDDING_PROVIDER=lexical` stores NULL vectors and makes no embedding-model calls;
meaning-based and visual search are explicitly disabled. The normal Gemini configuration
remains available. Switching provider later does not backfill existing NULL vectors;
previously indexed documents need reindexing before semantic retrieval can include them.

Run `python scripts/verify.py --e2e --audit` for automated validation. Install the test
browser once with `pnpm --filter @memora/web exec playwright install --with-deps chromium`.
An installed Chromium can be used via `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`. Verification
starts database/Redis services, migrates, checks lint, runs API tests (any skip fails),
runs browser-discovery tests, checks types/build/generated API contracts, audits production
npm dependencies, and runs browser acceptance tests in both deterministic-model and real
lexical modes. It saves reports under `data/test-reports/`. The GitHub Actions workflow
runs the same checks on pushes and pull requests; it has not run remotely until pushed.

The browser checks cover synthetic randomly named documents, real OCR, page opening,
multilingual queries, duplicate content, unavailable permissions, error recovery, library
isolation, deletion, responsive layouts, and automated accessibility checks. Their timing
measurements describe only the tiny local synthetic corpus. They do not certify all WCAG
requirements, production security, load capacity, all browsers/devices, or real-document
retrieval quality. The existing personal gold corpus is missing; its evaluation remains
blocked until consented source documents are available.

Research informing this pass: [Paperless-ngx search](https://docs.paperless-ngx.com/usage/)
combines document text and metadata; [Docspell search](https://docspell.org/docs/webapp/finding/)
shows matching passages. Memora now centers previews around matching words and preserves
Indic type hints instead of guessing types from arbitrary substrings. Broad fuzzy
expansion needs a measured retrieval corpus before it can be enabled confidently.

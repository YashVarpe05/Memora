# Phase 1 — OCR and PII masking

**Status: plan only. Nothing implemented pending approval.**

## Goal

Make images searchable, with Aadhaar and PAN numbers masked before any text leaves the
machine.

## What I read

- `docs/PRODUCT.md` — architectural rule 2: identifiers masked before embedding, required
  before OCR ships
- `docs/ROADMAP.md` — phase 1 definition of done, including the inspector requirement
- `apps/api/src/memora/services/extraction.py` — PyMuPDF block extraction, `is_pdf` sniff
- `apps/api/src/memora/api/routers/uploads.py` — PDF-only, rejects non-PDF with 415
- `apps/api/src/memora/bench/engines.py` — Paddle and Tesseract adapters already written
- `apps/api/src/memora/eval/inspect.py` — image rows read "text content unknown until OCR"
- `docker-compose.yml` — db and redis, both healthchecked
- Measured earlier: paddleocr 3.7 installs on Windows and dies in a oneDNN kernel at
  inference; `FLAGS_use_mkldnn=0` does not help

## Assumptions

**1. OCR is an HTTP service in compose, not an in-process import.** A `python:3.12-slim`
service with paddlepaddle, paddleocr and `tesseract-ocr`, exposing `POST /ocr`. The API
calls it over HTTP.

Alternatives considered: importing paddle into the API process fails on Windows, which is
where development happens; `docker exec` from the API is not a thing a service should do.
An HTTP boundary also means the ingestion worker in production is this same container,
which is the point — this is the production environment, not a workaround for a Windows
bug.

**2. Masking lives in the API's ingestion pipeline, not in the OCR service.** A PDF can
contain a PAN just as an image can. Masking placed after OCR only would miss
`mail.pdf`-shaped cases. It sits between extraction and chunking, so every text path
crosses it.

**3. Masked text replaces the identifier with a type token, not with `XXXX`.**
`[AADHAAR_NUMBER]` rather than `XXXX XXXX 9012`. Two reasons: partial masking still leaks
four digits and a format, and a type token makes the document *more* findable — "aadhaar"
becomes a term in the index, which is exactly what hero query 1 searches for. Say so if
you want UIDAI-style last-4 masking instead; it is a one-line change and a real tradeoff.

**4. Aadhaar detection uses the Verhoeff checksum, not just twelve digits.** Aadhaar
numbers carry a Verhoeff check digit. Matching bare 12-digit runs would mask phone
numbers, receipt IDs and dates-run-together. Checksum validation cuts false positives
sharply, and a false positive here silently destroys retrievable text.

**5. The original file is never masked.** Masking applies to extracted text — what gets
chunked, embedded and stored. The uploaded file stays byte-identical in local storage so
the viewer shows the real document. This is the distinction that makes the claim true:
the number stays on the machine, it just never enters the index or a prompt.

**6. Scope is Aadhaar and PAN only.** Phone numbers, bank accounts and card numbers are
not in scope for this phase. They are a natural extension and should be a deliberate
decision, not something that accretes.

## Files that will change

**Create**
```
infra/ocr/Dockerfile               python:3.12-slim + tesseract-ocr + paddle deps
infra/ocr/app.py                   POST /ocr -> {engine, text, ms}
infra/ocr/requirements.txt
apps/api/src/memora/services/ocr.py        HTTP client behind an OcrClient protocol
apps/api/src/memora/services/masking.py    Aadhaar + PAN detection and masking
apps/api/tests/test_masking.py
apps/api/tests/test_ocr_client.py
```

**Modify**
```
docker-compose.yml                         + ocr service, healthchecked
.env.example                               + OCR_URL, OCR_ENGINE
apps/api/src/memora/config.py              + ocr_url, ocr_engine, masking toggle
apps/api/src/memora/services/extraction.py + extract_image_blocks via OCR
apps/api/src/memora/api/routers/uploads.py accept images, not just PDF
apps/api/src/memora/eval/inspect.py        image rows carry real extracted text
apps/api/tests/test_uploads.py             image upload path
openapi.json, packages/core/src/types/api.ts   regenerated
```

## Implementation requirements

**OCR service.** `POST /ocr` takes image bytes and an optional engine name, returns
`{engine, text, ms}`. Tesseract and PaddleOCR both installed. Healthcheck confirms the
chosen engine can actually run — the benchmark already proved that "imports cleanly" and
"can run" are different things, and that check belongs in the container's healthcheck so
a broken engine surfaces at `docker compose up`, not at first upload.

**OCR client.** `OcrClient` protocol in the API, HTTP implementation plus a fake for
tests. No test makes a network call.

**Masking.** `mask_identifiers(text) -> tuple[str, list[Detection]]`. Detections are
counted and logged by type only — never the value, per the no-secrets-in-logs rule. Runs
on every extracted text path before chunking.

**Image ingestion.** `/uploads` accepts PNG, JPEG, WebP by magic-byte sniff, not
extension. Image text becomes a single block, chunked by the existing chunker. The
`Memory.source_type` becomes `image`.

**Inspector.** Image rows call the OCR service and show real extracted text. When the
service is unreachable the row degrades to today's message rather than failing the run —
the inspector must stay usable with compose down.

## Security requirements

- Masking runs before chunking, therefore before embedding, therefore before any hosted
  API call. This is the ordering that makes the `PRODUCT.md` claim true; a test asserts
  the embedder never receives an unmasked identifier.
- Detection counts are logged by type. Values never are.
- The OCR service binds to the compose network only. It is not published on a host port.
- The OCR service holds no credentials and reaches no external network.
- Uploaded bytes go to the OCR service and to local storage. Nowhere else.

## Acceptance criteria

1. `docker compose up -d` brings up an `ocr` service whose healthcheck passes only when
   the configured engine can complete an inference.
2. `POST /uploads` with a JPEG returns a memory id and chunk count > 0.
3. A JPEG containing a synthetic Aadhaar number is stored with `[AADHAAR_NUMBER]` in the
   chunk text, and the digits appear nowhere in the database.
4. A test asserts the embedder is never called with a string containing a valid Aadhaar
   or PAN pattern.
5. The uploaded file on disk is byte-identical to what was sent.
6. `uv run python -m memora.eval.inspect` shows extracted text for every image in
   `data/corpus/`.
7. The suite passes with compose down: OCR-dependent tests skip, masking tests do not.
8. Valid Aadhaar numbers are masked; 12-digit numbers failing the Verhoeff check are not.

## Checks to run

```
cd apps/api && uv run pytest && uv run ruff check .
docker compose up -d && docker compose ps
cd apps/api && uv run python -m memora.eval.inspect
pnpm gen:types && pnpm -C packages/core typecheck
```

## How to verify

1. `docker compose up -d` — the `ocr` service reports healthy.
2. `uv run python -m memora.eval.inspect` — every image row shows real text. The six
   WhatsApp screenshots either carry readable content or they do not, and that answer
   decides which gold queries are writable.
3. Upload one of the WhatsApp images and confirm a chunk count above zero.
4. Query the database directly for any twelve-digit run in `chunks.text`. Expect none.

```
docker exec memora-db psql -U memora -d memora -tAc "SELECT count(*) FROM chunks WHERE text ~ '[0-9]{12}'"
```

Expect `0`.

## Risks

**The OCR image is large and the first build is slow.** paddlepaddle plus its apt
dependencies runs to a few GB. Tesseract alone is small. If the build turns into a time
sink, tesseract-only is a working phase 1 and Paddle can be added when the benchmark runs
— flag it rather than spending an afternoon on a Dockerfile.

**Paddle on slim needs apt packages** — `libgomp1`, `libglib2.0-0`, `libgl1` at minimum.
Expect one or two build iterations to find them.

**Verhoeff has a false-negative mode too.** OCR misreads a digit, the checksum fails, the
number is not masked. Mitigation: mask on checksum failure as well when the surrounding
text contains an Aadhaar-ish cue word. Worth deciding, not worth guessing at now.

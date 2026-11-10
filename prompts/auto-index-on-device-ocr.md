# Auto-index on open, then on-device OCR (upload text, not files)

Status: PROPOSED 2026-11-07. Not approved. Nothing here is implemented.

## Goal
Open the app and search. No manual "Index" step, and on Android no document leaves the
phone: the device extracts and masks text, the server stores only masked text and metadata.
A search result still opens the original file, on the device that holds it.

## Today (read from code)
- Client enumerates files and POSTs each file's bytes to `POST /api/index/jobs`
  (`useDeviceScan.ts`, `routers/indexing.py`). The server stores the blob, a worker OCRs it
  (`worker.py`, `services/extraction.py`), then masks (`services/masking.py`) and indexes.
- Indexing starts only when the user presses Index and has consented.
- Web remembers chosen folders in IndexedDB (`discovery.browser.ts`) but rescans only on request.
- Android discovery plugin exists (MediaStore + `MANAGE_EXTERNAL_STORAGE`); no APK has been
  built and nothing here has run on a device since 2026-09-03.

## Step 1 - Auto-index on open (web and Android, existing upload path)
Smallest change, testable now.
- On app start, if the device is paired and online-consent was already given, run an
  incremental scan without a click. Reuse the existing per-path fingerprint skip
  (`size:modifiedAt`), so unchanged files cost nothing.
- Web: on load, restore saved folder handles. If permission is still `granted`, scan
  silently. If the browser asks again, show one "Re-allow folder access" button; never
  scan a folder the browser has not re-granted. Firefox/Safari have no directory handles,
  so they keep the manual folder pick.
- Android: scan on app resume, plus a WorkManager periodic job for background runs.
- Acceptance: add a file to a chosen folder, reopen the app, it appears in search with no
  click. Unit test for the "no consent -> no scan" and "permission lost -> no scan,
  no reconcile" paths (the latter must not mark files deleted).

## Step 2 - Android on-device extraction (the privacy step)
- Native plugin renders PDF pages (`PdfRenderer`) / reads images, runs ML Kit text
  recognition (Latin + Devanagari models, bundled) and uses the PDF text layer when present.
- Mask Aadhaar/PAN on device with a port of `masking.py` (Verhoeff check included), then
  send `{content_hash, filename, device_path, mime, size, pages:[{n, text}]}` to a new
  `POST /api/index/text-jobs`. The server re-masks anyway (defence in depth), chunks,
  embeds, stores the memory WITHOUT a blob.
- Open-from-result: on the owning device open by `device_path`; on another device show
  "stored on <device>" and fetch the file only on explicit request.
- Fall back to the existing upload path when on-device OCR fails or the user opts in.
- Acceptance: airplane-mode-free check that the request body contains no file bytes;
  the same 3 Hindi/Marathi/English synthetic documents used in the web e2e are found.

### Step 2, server half: IMPLEMENTED 2026-11-10 (client not built)
`POST /index/text-jobs` takes `{content_hash, filename, device_path, mime_type, byte_size,
pages:[{number,text}]}` and returns the same shape as `/uploads`. It re-masks, chunks,
embeds, classifies and stores a memory with no file; duplicates by `content_hash` attach
the new path. `/memories/{id}/file` answers 410 for these, and the viewer says the file may
be stored only on the device. No schema change: `content_hash` is the device's own hash.
Limits: 500 pages, 200,000 characters per page, 500,000 in total. Verified by 5 tests (masking,
no-file 410, search by content with a meaningless filename, dedupe, validation, size).
Not built: the ML Kit plugin and the phone client that calls it; the Android build and
install are unverified on a device. Indexing is synchronous in the request (no job row), so
the phone retries on failure.

### Step 2, client half: BUILT AND RUN ON AN EMULATOR 2026-11-10 (not a physical phone)
Android emulator (API 36, x86_64, Google APIs), debug APK, trial server over `adb reverse`.
- `TextExtractionPlugin.java` (ML Kit Latin + Devanagari, bundled) hashes the file, OCRs
  images and PDF pages (PdfRenderer, 40-page cap), reads text files; other types are rejected
  as "unsupported" and fall back to the existing upload. `packages/core/src/masking.ts` is a
  port of `masking.py` pinned to it by 10 parity tests; the phone masks before sending.
- Pairing by typed address and code, "Allow online indexing & scan": **6 checked, 6 sent, 0
  need attention**. Database check: 0 index jobs and no new blobs for that library, i.e. no
  file bytes reached the server. All 6 chunks have meaning vectors.
- On-device OCR results: image-only PDF read correctly (type: receipt); digital PDF read;
  Hindi "आधार कार्ड" card read, its Verhoeff-valid number masked to `[AADHAAR_NUMBER]` before
  sending (type: aadhaar); Marathi marksheet read (type: marksheet), plus a little Latin-model
  noise ("yorufachi / cahart 88") from running both recognisers on Devanagari; text file's PAN
  masked to `[PAN_NUMBER]`.
- Search in the app: "proof of my address" ranked the electricity bill photo first (Aadhaar
  second). Opening a result shows the image read from the phone, "This file is stored on this
  phone", and "Open on this phone", which handed the file to Google Photos. New endpoint
  `GET /memories/{id}/device-paths` (scoped to the caller's library) supports it.
- Not verified: a physical phone (real storage permission dialogs, camera QR pairing, real
  photo OCR quality, battery, thousands of files), opening a PDF through the system viewer,
  background scanning while the app is closed (no WorkManager), and fallback upload of
  Word/email files on the phone.

## Step 3 - Web on-device extraction (optional, after step 2)
Browser WASM OCR (tesseract.js) so a laptop that only hosts the UI also sends text only.
Slower and heavier than the server's Tesseract; do it only if hosting the server is the
privacy complaint. Not required to finish the project.

## Needs verifying before building (unknown today)
- ML Kit Devanagari accuracy on Hindi/Marathi Aadhaar-style scans: measure on the
  user's real 20 queries; do not assume.
- Whether `Memory` can exist without a blob (schema + `files.py` serving path).
- Chrome's persistent folder permission behaviour on the user's browser.
- Multilingual E5 size/latency on the phone (server-side embedding is the default; only
  move it on-device if measured).

## Not in scope
Hosting/deploy, multi-user auth, Ask-screen real answers, GraphRAG, new eval tooling.

## Gates (CLAUDE.md)
`uv run pytest && uv run ruff check .`, `pnpm typecheck && pnpm build`, `alembic upgrade head`,
gold-set eval, `pnpm gen:types` (new endpoint). Check `docker compose ps` first; a run with
containers down is not evidence.

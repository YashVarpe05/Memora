# Production readiness: what is true, what blocks it, in what order

Status: PROPOSED 2026-11-09. Research and code audit only; the one change made with it is
item P0-1. Everything else waits for approval, one batch at a time.

## What "production ready" means here
One owner, several devices (phone, tablet, laptop). Describe a document -> the right file
is rank 1 in seconds -> open it. Works when the laptop is off. Aadhaar/PAN never searchable
as raw numbers. Accuracy measured on the owner's real documents, not synthetic ones.

## Verified today (2026-11-09, containers up)
- 403 API tests pass, 0 skipped; ruff clean; web typecheck, build and 6 unit tests pass.
- Per-device libraries: `/pair/claim` mints a fresh `uuid4` identity per device
  (`services/pairing.py`); RLS applies per identity. A device cannot read another's library.
- Pairing codes are 128-bit, single-use, 5-minute TTL; only the digest is stored.
- Local E5 embedder is implemented and tested with mocks; real weights NOT yet verified
  (download of `intfloat/multilingual-e5-base` stalled at ~760 MB of ~1.1 GB).

## Blocking gaps, ranked
| # | Gap | Evidence | Fix | Needs |
|---|-----|----------|-----|-------|
| P0-1 | Production compose forces `GEMINI_API_KEY` and defaults to Gemini embeddings, so a server cannot start without an API account | `compose.production.yml` | provider env var, default `lexical`, key optional | nothing |
| P0-2 | Real semantic search unverified | download stalled | finish `--warmup`, then backfill and gold run | network |
| P0-3 | No real-document accuracy number | `context/my-queries.txt` blank; Recall@1 19/21 is the old gold set | owner writes 20 queries from memory, no ID numbers | owner |
| P0-4 | Phone cannot work with the laptop off | server only runs locally | deploy `compose.production.yml` to a small VPS (Hetzner is the steadiest for a Postgres workload; Oracle free tier risks reclamation; Fly.io has no free tier) | hosting + domain |
| P0-5 | No APK has ever been built since 2026-09-03 | SDK downloads failed | retry Android SDK install; build; run on the Galaxy S23 FE | network |
| P1-1 | `MANAGE_EXTERNAL_STORAGE` blocks Play Store; fine for a sideloaded personal APK | Google Play policy | SAF folder picker with persisted URI if the app is ever published | decision |
| P1-2 | Original Aadhaar scans sit unencrypted in `BLOB_ROOT` on the server | no app-level encryption in `storage.py` | full-disk encryption on the VPS now; keep originals on-device (on-device OCR plan) later | decision |
| P1-3 | On-device OCR so files need not be uploaded | `prompts/auto-index-on-device-ocr.md` step 2 | ML Kit Devanagari + on-device masking | P0-5 |
| P1-4 | Per-device revoke does not exist, only revoke-all | `pairing.py` | add a device id to status and a revoke-one endpoint | small |
| P2 | Ask tab still mock; refusal accuracy 2/4; no rate limits on the API | README, `main.py` | after P0 | |

## OCR engine
Research found no clean three-way benchmark on real Hindi scans. Tesseract with the Hindi
and Marathi traineddata is the best-supported choice; EasyOCR is reported to collapse on
real Devanagari scans. Keep Tesseract, and measure on the owner's own scans (P0-3).

## Aadhaar handling
Secondary sources say regulated entities must store only the masked form (first eight
digits hidden). A personal, single-owner library is a different case, but the app should
still never index the raw 12 digits - which `masking.py` already does before chunking and
embedding. Originals are kept so the owner can open them. Verify the legal position
against UIDAI's own circulars before any multi-user release.

## Order
1. P0-1 now. 2. P0-2 once the download finishes. 3. Owner writes `my-queries.txt` (P0-3).
4. P0-5 then P1-3. 5. P0-4 deploy. 6. P1-2 / P1-4.

## Gates
`uv run pytest && uv run ruff check .`, `pnpm typecheck && pnpm build`, `alembic upgrade head`,
gold eval after any retrieval change. A test run with containers down is not evidence.

# Wiring the scan — and the blocker found first

## Diagnosis, 2026-08-29

Checked in order. Containers, binding and reachability all pass; the failure is in the app.

| # | check | result |
|---|---|---|
| 1 | four containers healthy | **pass** — db, ocr, ollama, redis all healthy |
| 2 | API bound to `0.0.0.0` | **pass** — `uv run uvicorn memora.main:app --host 0.0.0.0 --port 8000` |
| 3 | reachable on the LAN | **pass** — `http://10.69.66.132:8000/health` returns 200 from the LAN address, not only loopback |
| 4 | a screen shows the pairing QR | **FAILS — nothing in `apps/web/src` calls `/pair/start` or renders a QR** |
| 5 | the built app's API base URL | **FAILS — the only call is `fetch('/api/search')`, relative, with no configurable base** |

**4 and 5 are one gap, not two.** Pairing exists in the API and in `usePairing.ts`, and
nothing in the UI uses either. So there is no QR to scan, *and* no mechanism by which the
phone could learn the laptop's address even if there were one.

In the browser this was invisible: Vite's dev proxy rewrites `/api/*` to
`localhost:8000`, so the relative URL worked. **In a Capacitor WebView there is no proxy —
`/api/search` resolves against the app's own origin and the phone calls itself.** The
symptom is a search that fails with no error anyone can act on.

### Verify from the phone before anything else

Open this in the phone's browser, on the hotspot:

```
http://10.69.66.132:8000/health
```

JSON means the network is fine and the problem is entirely in the app, which is what the
table above says. A timeout means the network is the problem and no app change can help —
check Windows Firewall on port 8000 and that both devices are on the same hotspot.

## What has to be built

1. **A pairing screen on the laptop** that calls `POST /pair/start` and renders the
   returned `{url, code}` as a QR.
2. **A pairing screen on the phone** that scans it and stores the token — `usePairing.ts`
   already does the exchange and storage; nothing calls it.
3. **A configurable API base.** Every request goes to the paired server's URL with the
   device token attached. `pairedFetch` exists; `useSearch` does not use it.

**The base URL must come from pairing, not from configuration.** A hotspot hands out a
different address each session, so a `.env` value would be stale by the next demo. This is
why the QR carries the URL as well as the code.

## Recorded decisions

### File types

**In:** images, screenshots, PDFs, and documents (`.docx`, `.txt`, `.md`).

**Audio and video:** only if MediaStore returns them as cheaply as the rest — the query is
already `MediaStore.Files` with a mime filter, so widening it is one line. But **neither has
an extraction path**: Whisper was descoped, and nothing reads video. Indexing a file that
can never be found by description adds rows to the corpus that dilute retrieval and cannot
be answered. **Documented as future work**, gated on an extractor existing rather than on
the scan being able to see them.

### First launch

**Offer both, default to newest-500.**

- *Quick start (default)* — the 500 most recent, then the rest in the background. Useful in
  about a minute.
- *Everything* — the full scan, stated as taking hours.

The default matters for the demo: an examiner watching a progress bar for two hours is not
a demo. It is also the honest default for a real user, who wants recent files first.

### What to skip

**Skip:** app caches (`/Android/data/`, `/Android/obb/`), thumbnail directories
(`.thumbnails`, `Pictures/.thumbnails`), anything under a `cache` or `tmp` path, and files
under ~10 KB, which are almost always icons or sprites.

**Keep WhatsApp media, deliberately.** `WhatsApp/Media/WhatsApp Images/` is exactly where
the forwarded screenshots live, and **three gold queries — q008, q009, q010 — target
them**. A generic "skip messenger media" rule would delete three measured results.

### Deleted files

**Keep the memory, mark it removed.** A file the user deletes from the phone should still
be findable, and the result should say
*"file removed from device on 14 March"* rather than failing to open.

Reasoning: the index holds masked text and vectors, not the document. Losing the search
history because a file was tidied away is the behaviour the product exists to fix — "I know
I had it" is the problem statement. **The blob is deleted; the record is not.** Erasure on
request stays a separate, complete operation and is unaffected.

Needs a `removed_at` column and a filter that keeps removed rows out of the default result
set unless nothing else matches.

## Acceptance

1. A QR appears on the laptop and the phone can pair from it.
2. After pairing, every request carries the device token and goes to the paired URL — no
   relative `/api` call survives in the native build.
3. A file the user never uploaded is discovered, indexed, and returned by description.
4. Quick start returns useful results in about a minute on a real gallery.
5. WhatsApp media is indexed; caches and thumbnails are not.

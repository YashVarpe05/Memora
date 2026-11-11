# Local mode: the phone works alone, with background indexing

Status: APPROVED by the user on 2026-11-12 ("when I open this app on a new device there is no
need to connect with the laptop and do setup... find out how to solve this"; "background scanning").

## The real obstacle
Zero-touch enrollment (prompts/zero-touch-enrollment.md) removes the setup, but it still needs a
server that is on. A free always-on server needs accounts only the owner can create. So a new
phone can only be "install and it works" today if the phone does not need a server at all.

## Decision
Add a LOCAL MODE that is the default when the APK is built without a server address. In local
mode the phone does everything itself: reads files (existing ML Kit OCR), masks Aadhaar, Virtual
ID and PAN, classifies the document type, stores the masked text in a private on-device SQLite
index, and searches it with word matching (BM25) plus document-type matching. No account, no
laptop, no network. Server mode (zero-touch enrollment to a hosted server) stays available for
builds that carry a server address.

## What local mode is NOT
- No meaning-based (semantic) search. That needs the embedding model, which is 1.1 GB; word
  matching, document types, filenames and Hindi/Marathi type words work. Measured on the owner's
  real library the word and type signals alone put the right document type first for most type
  queries; vague phrasings ("my school results") will miss more than with embeddings.
- No cross-device search. Libraries are already one per device by design.
- No server backup of the library; the index is rebuilt by rescanning.

## Design
- Native Java, package ai.memora.app. Pure, unit-testable parts: `Tokens` (port of
  lexical.words/tokens and its stop words), `Masking` (port of masking.py with Verhoeff),
  `DocTypes` (document_type.py vocabulary exported to `document_types.tsv`, with a Python test
  that fails if the two drift), `Ranker` (BM25 with the server's constants, type boost).
- `LocalIndex` (SQLiteOpenHelper): table docs and an FTS4 table of pre-tokenised words (the
  simple tokenizer treats every non-ASCII code point as a letter, so Devanagari works).
- `LocalIndexPlugin` (Capacitor): upsert, known, search, stats, prune, scheduleBackground.
- `ScanWorker` (WorkManager, periodic, battery-not-low): enumerates MediaStore, skips files whose
  size:modified fingerprint is already indexed, extracts, masks, classifies, upserts, and stops
  after about 8 minutes so the next run continues. Runs with the app closed.
- App: `isLocalMode()`; Index, Search, Viewer and Settings read from the plugin; the pairing gate
  is skipped; the first screen is the Index screen with one consent tap.

## Gates
Java unit tests (`gradlew testDebugUnitTest`) for tokens, masking parity, doc types, ranker;
Python parity test for the exported vocabulary; web typecheck, build and tests; a fresh emulator
install with NO server running: index synthetic Hindi/English documents, search them, close the app
and see the background worker index a newly added file; then the real phone.

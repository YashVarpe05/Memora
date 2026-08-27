# Capacitor + device auto-scan

**Plan only. Nothing implemented. Largest unbuilt thing in the project.**

Supersedes the scoping in `capacitor-device-indexing.md`, which assumed a Storage Access
Framework folder pick. The decision is now **auto-scan**, and two architectural questions
are resolved here rather than discovered during the build.

---

## 1. Where the pipeline actually runs — read this first

**This is the question that decides everything else, including CLIP.**

Today "nothing leaves the device" is true in a specific and slightly lucky way: *the device
is one machine.* The API, Postgres, Redis, the OCR container and Ollama all run on the same
laptop the browser runs on. Nothing crosses a network because there is no network to cross.

**A phone changes that, and it is the first thing since the local-stage-1 measurement that
could take the claim back.**

### What could and could not run on the phone

| component | on a phone? | what it would take |
|---|---|---|
| File discovery | **yes** | native APIs — the point of this phase |
| UI | **yes** | Capacitor wraps the existing build |
| Tesseract OCR | yes | Tesseract4Android exists |
| CLIP | yes | quantised int8 ONNX, ~150 MB — see §2 |
| Stage 1 (qwen 3B) | **marginal** | ~2 GB q4 via llama.cpp; runs, slowly |
| **Postgres + pgvector** | **no** | would have to become SQLite + sqlite-vec |
| **The API and repository layer** | no, as written | assumes async Postgres and RLS |

**A fully on-device build is technically conceivable and is a near-total rewrite of the
storage layer.** RLS — half the privacy novelty claim, enforced in Postgres and tested
against a non-superuser role — has no SQLite equivalent. It would have to be replaced by
something weaker and re-argued from scratch. That is not a phase; it is a different project.

### So: the phone talks to the user's own machine

The realistic architecture for this deliverable:

```
  phone (Capacitor)                        the user's own laptop
  ├── file discovery      ──── LAN ────►   FastAPI
  ├── search UI                            Postgres + pgvector (RLS)
  └── viewer / download                    OCR container
                                           Ollama (stage 1)
                                           CLIP
```

### What that does to the claim, stated precisely

The measured claim today is **"nothing leaves the device"**, and on a single machine it is
literally true. On the phone build it must become:

> **Nothing leaves devices the user owns.** Documents are discovered on the phone and
> processed on the user's own machine. No document, image, or query reaches a third party
> at any point.

**That is weaker in exactly one way and no more:** bytes cross a local network between two
machines the same person owns. It is still categorically different from every hosted
alternative, and the architectural rules that produce it are unchanged — rule 1 still
forbids document content in any prompt, masking still runs before embedding, RLS still
binds, and with local stage 1 the query still never reaches anyone else.

**What must not be claimed:** that the phone alone does the work. It does not. The report
should say *"discovery on the device, processing on a machine you own"* and not let "on my
device" imply more than file discovery and display.

**The honest framing, and it is still a strong one:** this is a personal-server
architecture. The comparison is not "phone-only versus cloud" — it is "your hardware versus
somebody else's", and that is the axis the whole project has been arguing along.

**Future work, with the obstacle named:** a fully on-device build needs SQLite + sqlite-vec
replacing Postgres + pgvector, and a replacement for the RLS guarantee. Both are real, both
are large, and the second is the one that costs a novelty claim.

---

## 2. CLIP on mobile — resolved by §1

`capacitor-device-indexing.md` recommended a quantised int8 ONNX build so the photo would
be embedded on the phone and never leave it. **Section 1 makes that pointless for privacy.**

If the phone already sends every discovered file to the user's machine for OCR, chunking,
embedding and storage, then **the image has already crossed the wire before CLIP is
reached.** Running CLIP on the phone would save a round trip and change nothing about what
leaves the device.

**Decision: CLIP stays server-side.** The 3.19 GB container never goes near a phone; it does
not need to.

- **Privacy cost: none**, given §1. The image crosses the same LAN as everything else.
- **Latency cost: none that matters.** Indexing is already a background job.
- **The ONNX work is not wasted, it is deferred** — it becomes necessary only in the
  fully-on-device architecture, where it would be one of several rewrites rather than an
  optimisation.

**The reasoning matters more than the decision.** On-device CLIP was justified by a privacy
argument that only holds if the *whole* pipeline is on-device. Once one component talks to a
server, per-component locality buys nothing. That is worth a sentence in the report, because
it is the kind of thing that gets built for a reason that stopped applying.

---

## 3. Permissions: auto-scan, and what it costs

**`MANAGE_EXTERNAL_STORAGE`** — full filesystem access, including `Downloads/` where fee
receipts and marksheets actually live.

**It is restricted on the Play Store and would block publication.** Google requires a
declaration and manual review, granted only for file managers, backup tools and antivirus.
Memora would not qualify.

**Acceptable here because the deliverable is a sideloaded APK**, granted directly by the
user. It is not acceptable for a published app, and the report must say so:

> The prototype requests `MANAGE_EXTERNAL_STORAGE` to scan device storage automatically.
> This permission is restricted on Google Play and would prevent publication in its current
> form. A publishable version would use the Storage Access Framework, where the user picks
> the folders to index once — more friction at setup, and a stronger consent story, at the
> cost of automatic discovery of files outside the chosen folders.

**Also request `READ_MEDIA_IMAGES`** for the gallery on Android 13+, which is unrestricted
and covers the majority case.

**Ask in context, never on first launch.** On the first scan the user starts, behind a
screen that says what will be read and where it goes — and §1 means that screen must say
"to your computer", not "nowhere". A permission dialog with no context is denied, and
Android does not ask twice.

---

## 4. First launch on a phone with thousands of files

Realistic: **8,000 photos, 400 screenshots, 60 PDFs.**

Scanning metadata is milliseconds. **The cost is OCR, embedding and upload**, and at ~1 s
per image that is over two hours of work.

**So the first pass is deliberately partial:**

1. **Newest first.** Recency dominates what people search for, and it makes the app useful
   in a minute rather than after two hours.
2. **Screenshots before camera photos.** Overwhelmingly text-bearing — receipts, tickets,
   job posts — so the highest yield per second.
3. **A visible cap on the first pass** — the 500 most recent — with the rest continuing
   under constraints.
4. **Progress the user can see**, and results that work while the index fills.
5. **Camera photos are worth indexing now**, which was not true before CLIP: a photo with no
   text used to produce nothing at all. **These two phases compound.**

## 5. Incremental scanning

A full rescan every launch would be unusable.

- **A high-water mark** on file mtime, persisted through `SecureStorage`. A rescan asks only
  for files newer than the marker.
- **Content-hash dedup already exists.** `find_by_hash` means an unchanged file costs one
  hash — no OCR, no embedding, no upload. The backfill path added recently means a
  re-encountered file can also *gain* a missing artifact rather than being skipped entirely.
- **Metadata filtering before bytes are read.** Extension and size come from the directory
  entry; a 4 GB video is excluded without being opened.

## 6. Battery and background limits

- **WorkManager**, with `requiresCharging` and `requiresDeviceIdle` for the bulk first pass.
  It can wait for a charger overnight — that is the honest place for two hours of work.
- **Incremental scans on foreground only**, cheap because of the high-water mark.
- **Resumable in batches**, so a scan interrupted at 60% resumes rather than restarting.
- **Never a foreground service.** A persistent notification for a personal search index is
  what gets an app uninstalled.

## 7. Platform interfaces

`packages/core/src/platform/` already defines these with web implementations. Capacitor
supplies native ones — this is why `PORTABILITY.md` was enforced from the start.

| interface | native implementation |
|---|---|
| `SecureStorage` | Capacitor Preferences over Android Keystore |
| `CaptureProvider` | platform camera |
| `OfflineQueue` | native persistence, survives process death |
| `PushProvider` | FCM |
| `Navigator` | unchanged |

**One is new and is the work of this phase:**

```ts
export interface FileDiscovery {
  isSupported(): Promise<boolean>;
  requestPermission(): Promise<PermissionState>;
  scan(options: ScanOptions): AsyncIterable<DiscoveredFile>;
  since(marker: string): AsyncIterable<DiscoveredFile>;
}
```

`DiscoveredFile` carries path, size, mtime and mime — **not bytes**. The web
implementation returns `isSupported() === false`, which keeps the PWA building and puts the
platform boundary in code rather than a comment.

## 8. What the demo looks like

1. Install the APK. Open it. It finds the laptop on the LAN.
2. Tap **Scan my phone**. The permission screen explains what is read and that it goes to
   your own computer.
3. Progress fills. Within a minute the recent screenshots are searchable.
4. Type *"the whatsapp message from aradhana"* — the right screenshot, rank 1, on a phone,
   from files nobody uploaded by hand.
5. Tap it, view it, download it.
6. Type *"my passport"* — **"I don't have that."**

**Step 4 is the whole project in one screen**, and step 6 is the only one an examiner will
not expect.

---

## 9. Size, honestly — and what gets cut

**This does not fit alongside the report in the time left, and planning all of it would be
dishonest.**

| part | size | verdict |
|---|---|---|
| Capacitor shell wrapping the existing build | small | **ships** |
| LAN discovery + config of the server address | small | **ships** |
| `FileDiscovery` interface + Android implementation | **medium** | **ships** |
| Permission flow with the consent screen | small | **ships** |
| First-pass scan, newest-first, capped at 500 | medium | **ships** |
| Upload pipeline reusing `/uploads` | small | **ships** |
| Incremental rescan with a high-water mark | medium | **documented** |
| WorkManager background scanning | **medium-large** | **documented** |
| Offline queue surviving process death | medium | **documented** |
| On-device CLIP / stage 1 / SQLite | **very large** | **documented, §1–2** |

**What ships is the sentence being true:** the app finds files on the phone that nobody
uploaded, indexes them, and searches them. **What is documented is everything that makes it
pleasant to live with** — background scanning, resumability, offline behaviour.

**If time runs short inside this phase, cut in this order:** WorkManager first (a
foreground-only scan still demonstrates the capability), then the 500-file cap can become a
smaller number, then LAN auto-discovery can become a typed-in address.

**Do not cut the permission consent screen.** It is where the privacy story is told, and §1
means it is also where the architecture is stated honestly to the user.

## 10. Acceptance

1. A file the user never uploaded is discovered on the phone, indexed, and returned by a
   description. That is the sentence.
2. The consent screen says where files go — *"to your computer"* — and §1 is not implied
   away anywhere in the UI.
3. `packages/core` still compiles with `"DOM"` omitted. Native types must not leak in.
4. No component calls a Capacitor plugin directly; everything goes through `platform/`.
5. `MANAGE_EXTERNAL_STORAGE` and its Play Store consequence are recorded in the report, with
   the SAF alternative named.
6. A phone with thousands of files returns useful results within a minute.

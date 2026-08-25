# Capacitor + device file indexing

**Plan only. Nothing implemented. This is the largest unbuilt thing in the project and it
has not started.** The sizing section at the end is the part to read first if time is short.

## Why this is not optional any more

The product sentence is *"it searches the files already on your phone."* Today the system
searches **files the user has uploaded to it**. Those are different products, and the second
one asks the user to gather their documents first — which is the problem being solved.

**A PWA cannot close this gap.** Browsers sandbox storage deliberately:

- there is no web API that enumerates a gallery or a Downloads folder
- the File System Access API grants handles to **user-picked** files and directories, on
  desktop; it is not device-wide scanning and it is not available on Android Chrome for
  directories in the way this needs
- there is no background execution model that would let a web app notice a new file while
  the app is closed

This is a platform boundary, not a missing feature or an engineering shortfall. Either a
native shell exists or the sentence is false.

## What Capacitor actually changes

**Less than it appears, because `PORTABILITY.md` was enforced from the start.** That
discipline — business logic in `apps/api` and `packages/core`, components render and
dispatch only, platform capabilities behind interfaces, Bearer tokens rather than
httpOnly-cookie-only, `fetch` + `ReadableStream` rather than `EventSource`, Tailwind
utilities only — was paid for over many sessions specifically so this phase would be an
implementation of existing interfaces rather than a rewrite.

**`apps/web` is 14 TypeScript files.** It is a thin shell, as intended. Capacitor wraps the
built Vite output; the React code largely does not change.

### The interfaces that get native implementations

`packages/core/src/platform/` already defines these, with web implementations today:

| interface | web today | native |
|---|---|---|
| `SecureStorage` | web storage | Capacitor Preferences, backed by Android Keystore |
| `CaptureProvider` | `getUserMedia` + `MediaRecorder` | platform camera |
| `OfflineQueue` | in-browser | native persistence, survives process death |
| `PushProvider` | web push | FCM |
| `Navigator` | web routing | unchanged |

**One interface does not exist and has to be designed: file discovery.** Nothing in
`platform/` enumerates device storage, because until now nothing could. That is the genuinely
new work, and it is the point of the phase.

```
export interface FileDiscovery {
  isSupported(): Promise<boolean>;
  requestPermission(): Promise<PermissionState>;
  /** Enumerate candidates. Async iterable, because a device may hold thousands. */
  scan(options: ScanOptions): AsyncIterable<DiscoveredFile>;
  /** Files added since a marker, so a rescan is not a full rescan. */
  since(marker: string): AsyncIterable<DiscoveredFile>;
}
```

`DiscoveredFile` carries a path, size, mtime, and mime — **not bytes**. Bytes are read only
for files that pass filtering, or a scan loads gigabytes into memory.

The web implementation returns `isSupported() === false`. That keeps the PWA building and
running, and makes the platform boundary explicit in code rather than in a comment.

## Background indexing without draining the battery

The naive design — watch the filesystem continuously — is what makes an app get uninstalled.

**Do not run continuously. Run on triggers, batched, under constraints.**

- Android **WorkManager**, with `requiresCharging` and `requiresDeviceIdle` for the initial
  bulk scan. That is the expensive one and it can wait for a charger overnight.
- Incremental scans on app foreground, cheap because they use `since(marker)`.
- **Filter before reading bytes.** Extension and size are free from directory metadata; a
  4 GB video is excluded without opening it.
- **Content-hash dedup already exists** and does the heavy lifting: `find_by_hash` means a
  rescan of an unchanged file costs one hash, no OCR and no embedding.
- **Cap per batch.** A fixed ceiling of files per run, resumable, so a scan interrupted at
  60% resumes rather than restarting.

**The expensive step is not scanning, it is OCR and embedding.** Scanning ten thousand file
entries is milliseconds. OCR at ~1 s per image and an embedding call per chunk is the real
budget, and it is why the pipeline must be a resumable queue rather than a loop.

## Android permissions

Android 13+ replaced `READ_EXTERNAL_STORAGE` with granular media permissions:

| permission | for |
|---|---|
| `READ_MEDIA_IMAGES` | photos and screenshots — **the main one** |
| `READ_MEDIA_VIDEO` | not needed; do not request it |
| `MANAGE_EXTERNAL_STORAGE` | full filesystem, including PDFs in Downloads |

**`MANAGE_EXTERNAL_STORAGE` is the hard problem and it needs a decision, not a default.**
It is the permission that reaches PDFs in `Downloads/`, which is where fee receipts and
marksheets actually live. Google Play treats it as high-risk and requires a declaration and
review to ship. For a college project distributed as an APK it is grantable by the user
directly, but it is an intimidating system dialog — *"Allow Memora to access all files?"* —
and it undercuts the privacy pitch at exactly the moment the examiner is watching.

**Recommended:** request `READ_MEDIA_IMAGES` only, and use the **Storage Access Framework**
folder picker for documents — the user picks `Downloads/` once, deliberately, and the app
gets persistent scoped access to it. Slightly more friction, far better story: *"you chose
this folder, and nothing outside it is visible to the app."* That is a demo asset rather
than a liability.

**Ask at the right moment.** Not on first launch. On the first scan the user initiates,
with a screen that says what will be read and that nothing is uploaded. A permission dialog
with no context is denied, and Android does not ask twice.

## First launch on a device with thousands of files

The realistic case: **8,000 photos, 400 screenshots, 60 PDFs.**

Scanning is trivial. OCR and embedding are not: 8,400 images at ~1 s of OCR each is over two
hours of CPU, and embedding every result is thousands of API calls.

**So do not index everything, and be explicit that this is a choice:**

1. **Newest first.** Sort by mtime descending. Recent files are what people search for, and
   it makes the app useful within a minute instead of after two hours.
2. **Screenshots before camera photos.** Screenshots are overwhelmingly text-bearing —
   receipts, tickets, job posts — and they are the highest yield per second of OCR.
3. **A visible cap on the first pass**, e.g. the 500 most recent, with the rest continuing
   in the background under WorkManager constraints.
4. **Progress the user can see**, and a result set that works while it fills. An empty screen
   for two hours reads as broken.
5. **Skip what cannot help.** Camera photos with no text produce nothing — until CLIP exists,
   at which point they become the thing that makes the gallery searchable. **These two phases
   compound: CLIP is what makes indexing 8,000 photos worth the battery.**

## Sizing, honestly

**This does not fit alongside everything else, and pretending otherwise is how a final-year
project misses its deadline.**

What is genuinely left, with rough shape:

| work | size | status |
|---|---|---|
| Finish 3d | tiny | armed |
| CLIP | **medium** | planned, not started |
| **Capacitor + device indexing** | **large** | planned, not started |
| **Search UI — list, viewer, download** | **medium-large** | **not started, and there is no search screen at all** |
| Auth | small-medium | not started |
| Gmail connector | medium | not started |
| Report, UML, paper | large | not started |

**Two things deserve emphasis.** First, there is **no search UI whatsoever** — the degraded
banner currently lives in a chat view because that is the only screen that exists. The
entire measured retrieval system has no interface. Second, `PRODUCT.md` says *"the answer is
the file, and a file you cannot open is not an answer"* — which makes the viewer part of the
core claim, not polish.

### What gets cut, and why

**Cut the Gmail connector.**

That is uncomfortable, because `PRODUCT.md` lists it under "never cut" and argues that
upload-only makes this NotebookLM. The argument was right when uploading was the only intake
path. **Device indexing satisfies the same requirement better**: it is a live, automatic
source that does not ask the user to gather anything, and it is the one the product sentence
actually promises. Gmail was the proof that documents arrive without being filed; the device
scanner proves it more directly and on the platform the product is about.

So the "never cut" line should be amended to *"at least one automatic, non-upload intake
path"*, satisfied by device indexing, with Gmail as documented future work.

**Do not cut the search UI.** It is smaller than Capacitor and without it there is nothing to
demonstrate. A measured 0.947 with no screen is a number in a document.

### Recommended order

1. **Finish 3d** — armed, costs nothing, closes the phase
2. **Search UI + viewer + download** — makes everything already built visible and demoable.
   Do this before any new capability
3. **CLIP** — highest value per unit effort, unblocks `document_identity` and query 7
4. **Capacitor + device indexing** — makes the product sentence true
5. **Auth** — small, needed before anyone but the developer runs it
6. **Report** — start in parallel, not after
7. ~~Gmail connector~~ — documented future work

**Step 2 before step 3 or 4 deliberately.** The riskiest state to be in is having built two
large new capabilities and no way to show any of it. A working search screen over the
existing 0.947 is a complete, demonstrable product; everything after it is an upgrade to
something that already works.

**If time runs out after step 3**, the project still has: measured two-stage retrieval, a
working UI, visual search, the privacy architecture, and an honest chapter on why the native
shell is required and what it would take. That is a strong submission. A half-finished
Capacitor migration with no search screen is not.

## Acceptance, if it is built

1. `FileDiscovery` is an interface in `packages/core/platform`, with a native implementation
   and a web one that reports unsupported. No component calls a Capacitor plugin directly.
2. The initial scan is resumable and survives process death.
3. `READ_MEDIA_IMAGES` plus SAF folder selection. `MANAGE_EXTERNAL_STORAGE` is not requested
   without an explicit decision recorded here.
4. Permission is requested in context, never on first launch.
5. A device with 8,000 files returns useful results within one minute.
6. `packages/core` still compiles with `"DOM"` omitted from tsconfig. Native types must not
   leak in — that constraint is what made this phase cheap, and it is easy to break here.

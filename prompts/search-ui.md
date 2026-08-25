# Search UI — the screen the whole project has never had

**Plan only. Nothing implemented.**

## Why this comes before CLIP and Capacitor

Layer one is measured at Recall@1 0.947 and **has no interface**. The degraded banner lives
in a chat view because the chat view is the only screen that exists. Every number in
`BASELINE.md`, `PHASE3.md`, `PHASE3C.md` and `PHASE3C-NOSKIP.md` describes a system nobody
has ever seen work.

`PRODUCT.md` says *"the answer is the file, and a file you cannot open is not an answer."*
By that standard layer one is not finished — it returns a ranked list to a test harness.

**This is the demo.** The sequence an examiner remembers is: type a description in your own
words → the right document appears first → tap it → read it → download it. Under a minute,
no explanation needed. That sequence has never run.

## Built against the real corpus

**No mocks.** Eleven documents and 377 chunks are already indexed under `EVAL_USER_ID`, and
the gold set is 21 real queries with known correct answers. The UI gets pointed at that.

The difference matters: a mocked list renders whatever shape is convenient. The real corpus
has a 4-page PDF with no text layer, WhatsApp screenshots with filenames like
`WhatsApp Image 2026-07-03 at 01.24.47 (1).jpeg`, a 353-chunk calendar, and three files with
no extractable text at all. **Those are the cases that break a layout**, and they are the
cases the report screenshots will contain.

Typing "the whatsapp message from aradhana" and getting the right jpeg at rank 1 is the
acceptance test, not a rendered card with lorem ipsum.

## Scope

**In:**

| | |
|---|---|
| Search input | one field, the user's own words. `POST /search`, never GET — a personal description must not enter a URL or an access log |
| Ranked result cards | thumbnail, title, filename, source type, matched snippet, rank |
| Document viewer | PDFs paged, images zoomable |
| Download | the file, by its real name |
| Degraded banner | **moved here from the chat view** |

**Out:** chat, auth, upload UI beyond what exists, filters as UI controls, infinite scroll,
search history, sharing.

### The banner moves, and why that is not cosmetic

It currently polls `/health/ready` from the chat view — correct only because there was
nowhere better. **The degradation harms search results**, so the warning belongs on the
search screen. A warning on a page the user never opens is not a warning.

It should also read the **per-response** `degraded_message` that `POST /search` already
returns, not only the polled readiness state. The response knows about *this* search; the
poll knows about the process. Prefer the response, fall back to the poll.

## Endpoints, all of which exist

```
POST /search                          → results[], filters, degraded_message, stage1_*
GET  /memories/{id}/file              → the document
GET  /memories/{id}/thumbnail         → card image
```

Nothing new is needed on the API. Types come from `packages/core/src/types/api.ts` via
`pnpm gen:types` — **never hand-written**, per `PORTABILITY.md`.

## Mobile-first at 375px

The product is a phone app and every report screenshot will be from a phone.

- 375px is the design target, not a breakpoint to degrade into
- **Tailwind utilities only**, NativeWind-compatible — this screen gets carried into the
  Capacitor build unchanged, so a `grid` or a non-portable class here becomes a rewrite later
- flexbox over CSS grid
- tap targets ≥ 44px
- the viewer is full-screen on mobile, not a modal-in-a-modal

### Shape

```
┌─────────────────────────┐
│  [ describe it…      ]  │  ← focused on load
├─────────────────────────┤
│ ⚠ query understanding   │  ← only when degraded
│   unavailable…          │
├─────────────────────────┤
│ ┌────┐ 1. Fee Receipt   │
│ │thmb│ receipt.pdf · PDF│
│ └────┘ "…semester seven │
│        payment…"        │
├─────────────────────────┤
│ ┌────┐ 2. …             │
└─────────────────────────┘
```

Rank is shown. It is the metric the project is measured on, and showing it makes the demo
legible — the examiner sees "1" next to the right answer.

## States that must be designed, not discovered

The real corpus produces all of these:

| state | why it happens here |
|---|---|
| **Empty** — before first search | The default. Needs example queries, since "describe it in your own words" is a new interaction and users will not guess. |
| **Searching** | Stage 1 costs **2–3 seconds**, measured. That is far too long for an unexplained spinner, and it is the single worst UX fact about this system. Say what is happening. |
| **No results / refused** | q020 and q021 exist precisely for this. "I don't have that" is a correct answer and must not look like a crash. |
| **Degraded** | Banner above results. Results still shown — degraded, not broken. |
| **No thumbnail** | Three corpus files have no extractable text; some have no thumbnail. Needs a type-based placeholder, not a broken image. |
| **Long filename** | `WhatsApp Image 2026-07-03 at 01.24.47 (1).jpeg` must truncate without breaking the card. |
| **Viewer failure** | A PDF that will not render needs a download fallback, not a blank screen. |

**The 2–3 second wait deserves a decision rather than a spinner.** Options: show the stage-1
filters as they arrive so the user sees the system understood them; or run the search
unfiltered first and re-rank when stage 1 returns. The second is more work and better, and
it is also the mitigation `PHASE3.md` already lists for latency. **Pick one deliberately and
write down which.**

## Files

**Create**
```
apps/web/src/features/search/SearchView.tsx        screen
apps/web/src/features/search/SearchInput.tsx
apps/web/src/features/search/ResultCard.tsx
apps/web/src/features/search/DocumentViewer.tsx
apps/web/src/features/search/useSearch.ts          state; calls the API, holds nothing else
```

**Modify**
```
apps/web/src/App.tsx                    route search as the default screen
apps/web/src/components/AppShell.tsx    nav
apps/web/src/features/chat/ChatView.tsx remove the banner
```

**`useSearch.ts` holds no logic beyond request and state.** Ranking, filtering and fusion
are the API's, per `PORTABILITY.md`. A component that sorts results has moved business logic
into the shell and will have to be undone for mobile.

## Predictions

Not a measurement, so these are design predictions to check against reality:

| # | prediction |
|---|---|
| 1 | The calendar `.ics` will look wrong on a card. It is 353 of 377 chunks and wins queries it should not — its snippet will be a fragment of an event with no useful title. The card design must survive a document that is mostly noise. |
| 2 | Thumbnails will be missing more often than expected. Generation is best-effort at ingest and three files have no text at all. |
| 3 | The 2–3 s wait will feel much worse in a browser than it does in a test harness. |
| 4 | Rank 1 being correct 18 times out of 19 will feel **less impressive** than the number suggests, because the one miss is visible and the successes look unremarkable. That is worth knowing before the defence. |

## Acceptance

1. Typing "the whatsapp message from aradhana" against the real indexed corpus returns the
   correct jpeg at **rank 1**, visibly numbered.
2. Tapping it opens the image; it can be downloaded under its real filename.
3. A gold PDF query opens a readable, pageable PDF.
4. q021 "my college fee receipt" produces a comprehensible empty state, not an error.
5. Renders at **375px** with no horizontal scroll. Verified in the browser, screenshot taken.
6. The banner appears on the search screen when stage 1 is degraded, and is gone from chat.
7. `pnpm typecheck` and `pnpm build` pass; no hand-written API types.
8. Long filenames and missing thumbnails handled, checked against the real corpus.

## Risks

**Scope creep into filters and chat.** Once results render, adding a source-type dropdown is
tempting. Stage 1 already extracts filters from the words; a UI filter competes with the
product's whole thesis. **Out of scope, deliberately.**

**The viewer is the part most likely to overrun.** In-browser PDF rendering is genuinely
fiddly. If it does, ship images inline and PDFs as download-plus-first-page-thumbnail; the
answer is still the file. Do not let the viewer delay the searchable list.

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

### Decided: search unfiltered first, re-rank when stage 1 returns

Not a spinner. **Fire both arms in parallel and let the screen improve.**

```
on submit ──┬─► POST /search {stage1: false}  → ~50 ms  → render immediately
            └─► POST /search {stage1: true}   → 2–3 s   → re-rank in place
```

Both endpoints exist; `stage1: false` is the ablation switch already used by the harness.
**No API change is needed** — this is two requests from the client, and the second replaces
the first's ordering when it lands.

Why this and not the alternative:

- **Something correct is on screen in 50 ms.** The dense-only arm is Recall@1 0.842, so the
  right document is already first about five times in six. The stage-1 arm improves it to
  0.947, which is a re-rank, not a rescue.
- **It degrades into the good case.** If stage 1 fails — quota, transport, parse — the user
  already has results and the banner explains why they may be worse. Compare the spinner
  design, where a failure turns three seconds of waiting into an error. That is the worst
  possible version of the demo-day failure the whole guard exists to prevent.
- `PHASE3.md` already names this as the latency mitigation, so it is a recorded decision
  being executed rather than a new idea.

**Cost: two query embeddings per search instead of one.** At $0.15/1M that is ₹0.0006 —
below noise, and the reason it is affordable is `quota-ceiling-decision.md`.

**The re-rank must be visible, not sneaky.** Rows silently reordering under a reading user
is disorienting. Animate the reorder, and mark the transition — this is where the extracted
filters appear, so the movement has a visible cause.

## Showing the work, because a correct result looks like nothing happened

**This is a design requirement, not decoration.** 18 of 19 at rank 1 sounds impressive and
will not *feel* impressive, because success looks like a list appearing. Nothing on screen
says the system understood "the mail yash sent to rutuja" as a sender plus a document type,
searched inside that, and ranked the answer first. The examiner sees a search box that
worked, which is what every search box appears to do.

**The fix is in the UI, not in retrieval.** Retrieval is already at 0.947. What is missing is
evidence of the work.

Every field below is **already in the `POST /search` response.** Nothing new is computed.

### 1. The extracted filters, as chips

When the stage-1 arm returns, show what it understood, above the results:

```
understood:  [ from: aradhana ]  [ type: chat ]  [ image ]
```

This does triple duty: it proves stage 1 ran, it explains why the list just re-ranked, and it
**is the two-stage architecture made visible** — the project's central contribution, on
screen, without a word of explanation. From `filters` in the response.

When stage 1 is skipped by the signal heuristic, say so plainly — *"no filters needed"* —
rather than showing nothing. An empty row is ambiguous between "skipped" and "failed", and
this project has spent real effort keeping those distinct in the API. Throwing that away at
the last inch would be a waste.

### 2. Query terms highlighted in the snippet

The card already carries `snippet` from the matching chunk. Highlight the query's terms
inside it. It answers "why this one" in the place the eye already is, and it makes the
match a fact the user can check rather than a claim.

Highlight in the component, never server-side — the API returns data, the shell renders it.

### 3. Why this document ranked first

The response carries both `score` and `raw_score`, and the difference is exactly the filter
bonus. On the top result:

```
rank 1 · matched on content + sender + type
```

Derived from which filters the document satisfies. It turns `FILTER_BONUS = 0.08` from an
implementation detail into the visible reason the right answer won.

### 4. The one miss, handled deliberately

q019 misses in every arm because its file has no extractable text. **Do not hide it.** A
system that says *"three of your files contain no readable text and cannot be found by
description yet"* is more credible than one that silently returns nothing — and it sets up
the CLIP phase as the answer to a problem the examiner has already seen.

### What not to do

**Do not add a debug panel.** This is the product surface, not an inspector. Everything above
is a sentence or a chip in the normal flow; if it needs a toggle, it is too much.

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
| 4 | Rank 1 being correct 18 times out of 19 will feel **less impressive** than the number suggests, because the one miss is visible and the successes look unremarkable. **This prediction is now designed against** — see "Showing the work" above. If the filter chips and the match explanation do not fix it, the problem is the demo script, not the UI. |

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
9. Results appear in well under a second, before stage 1 returns, and re-rank visibly when
   it does. If stage 1 fails, the first results stay on screen and the banner explains.
10. The extracted filters are visible on screen after a stage-1 search, and a skipped
    stage 1 is distinguishable from a failed one **in the UI**, not just in the response.

## Risks

**Scope creep into filters and chat.** Once results render, adding a source-type dropdown is
tempting. Stage 1 already extracts filters from the words; a UI filter competes with the
product's whole thesis. **Out of scope, deliberately.**

**The viewer is the part most likely to overrun.** In-browser PDF rendering is genuinely
fiddly. If it does, ship images inline and PDFs as download-plus-first-page-thumbnail; the
answer is still the file. Do not let the viewer delay the searchable list.

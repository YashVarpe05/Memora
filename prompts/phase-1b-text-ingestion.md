# Phase 1b — text ingestion: calendar, email, chat

**Status: plan only. Nothing implemented pending approval.**

## Goal

Make `.ics`, `.eml` and WhatsApp `.txt` exports ingestable, chunked per format, with
timestamps on the chunk record — so `temporal_resolution` gold rows are gradeable rather
than passing the gate and failing at baseline.

## What I read

- `docs/PRODUCT.md` — the stage 1 filter contract: `sender`, `date_range`, `source_type`,
  `has_attachment`, `entities`
- `apps/api/src/memora/api/routers/uploads.py` — PDF and image only; everything else 415s
- `apps/api/src/memora/services/chunking.py` — one token-window strategy, `Block`-based
- `apps/api/src/memora/services/search.py` — `SEARCH_FANOUT = 5`, measured against a
  20-chunk corpus
- `apps/api/src/memora/db/models/chunk.py` — `ordinal`, `page`, no time, no sender
- The real corpus: 355 calendar events, 31 of them recurring

## Assumptions

**1. Chunk-per-event breaks the fetch window, and that is the biggest consequence here.**

Measured, not guessed:

```
current corpus       20 chunks total
fetch window         50 chunks at limit=10
the calendar alone   355 events -> 355 chunks
window coverage      14% of the calendar, before any other document exists
```

One file becomes seventeen times the entire current corpus. The over-fetch bound I
measured two commits ago said coverage held to roughly twenty documents — that estimate
assumed 2.5 chunks per document, and a calendar is 355.

Two things follow. `SEARCH_FANOUT` has to be revisited as part of this work rather than
after it, and the baseline must be recorded *with* the calendar ingested, or it measures
a corpus that no longer exists.

I would rather raise the fanout and re-measure than let the first real ingest silently
shrink recall. **This is the assumption most worth arguing with.**

**2. Recurring events are stored once, not expanded.** 31 of the 355 carry an `RRULE`.
Expanding a daily event over four years is tens of thousands of chunks from a single
calendar entry. The rule is stored as metadata; resolving "the interview in February"
against a recurrence is phase 4's problem, not ingestion's.

**3. `icalendar` as a dependency; email and chat need none.** Folding, `TZID`, `RRULE`
and escaping are the kind of thing that looks like forty lines and is not. `email` is
stdlib and handles multipart properly. WhatsApp is regex either way.

**4. Time gets a column, because a date range is a filter and not a similarity.**
`Chunk.occurred_at` — when the content is *about*, distinct from `created_at`, which is
when it was ingested. Without it "the fee receipt from last semester" is a semantic match
against the words "last semester", which is not the same question.

**5. Structured extras go in a JSONB `meta`, with `sender` promoted to a column.**
`sender` is named in the stage 1 filter contract, so it will be filtered on and wants an
index. Location, participants, recurrence rule and message counts will not be filtered on
in phase 4 and do not need columns yet.

**6. WhatsApp export parsing is locale-fragile.** The line format varies by app version
and phone locale — `[DD/MM/YY, HH:MM:SS] Name:` and `DD/MM/YYYY, HH:MM - Name:` are both
real. Two patterns, and a file matching neither is rejected with a message saying so
rather than silently producing one enormous chunk.

**7. Attachments are out of scope, and that is a problem worth naming.** Hero query 2 is
"the PDF a professor sent" — which needs the *attachment* to be findable, not the email
body mentioning it. Making an attachment its own `Memory` linked to the email is the
right design and it is a phase of its own. Flagged here so it is a scheduled decision
rather than something discovered when q002 fails.

## Files that will change

**Create**
```
services/parsers/__init__.py
services/parsers/calendar.py     VEVENT -> events, no recurrence expansion
services/parsers/email.py        headers + preferred text body
services/parsers/chat.py         WhatsApp export -> conversation windows
migrations/versions/0003_chunk_time_and_meta.py
tests/test_parser_calendar.py
tests/test_parser_email.py
tests/test_parser_chat.py
tests/test_text_ingestion.py
```

**Modify**
```
db/models/chunk.py         + occurred_at, meta
db/models/memory.py        + sender, occurred_at
services/extraction.py     + text_mime sniffing and dispatch
services/chunking.py       Block gains occurred_at and meta
api/routers/uploads.py     accept text formats, set source_type
services/search.py         SEARCH_FANOUT revisited and re-measured
pyproject.toml             + icalendar
```

## Implementation requirements

**`.ics` — one chunk per event.**

Chunk text is the human-readable rendering: summary, when, location, description. The
start time also goes to `occurred_at`, and the recurrence rule to `meta`. An event with
no `SUMMARY` and no `DESCRIPTION` is skipped — a bare busy-block is not a document
anyone searches for. `source_type` is `calendar`.

**`.eml` — headers as metadata, body chunked normally.**

`From` populates `Memory.sender`, `Date` populates `occurred_at`, `Subject` becomes the
title and the contextual prefix. `get_body(preferencelist=("plain", "html"))`, with tags
stripped when only HTML exists. The body is chunked by the existing token window, because
an email body is prose. `source_type` is `email`.

**WhatsApp `.txt` — conversation windows.**

Group consecutive messages, breaking on a gap of 30 minutes or 20 messages, whichever
comes first. One message embeds badly; a window reads like a conversation. Participants
and the window's date range go to `meta`, the window start to `occurred_at`. The export's
"Messages and calls are end-to-end encrypted" preamble is dropped. `source_type` is
`chat`.

**Masking runs on all three**, unchanged. `.eml` and chat exports are where an Aadhaar or
PAN actually appears as plain text rather than inside a photo — this is the path the
masking work was written for.

## Security requirements

- Masking is applied to every extracted text path, so all three go through it. The
  existing `require_masked` gate at the embedder means a new path that forgot would fail
  rather than leak.
- `.eml` parsing must not follow external references — no remote images fetched while
  rendering an HTML body, no link resolution.
- Sender and participant strings are stored as data. They are never used to build paths.
- Calendar and chat files often contain other people's data. That is inherent to the
  product and covered by per-owner isolation; it is not a reason to treat these files
  differently, but it is a reason not to log their contents.

## Acceptance criteria

1. Uploading the real `.ics` yields one chunk per named event, and no recurrence is
   expanded.
2. Every calendar chunk carries `occurred_at`.
3. An `.eml` yields `Memory.sender`, a subject-derived title, and `occurred_at` from the
   `Date` header.
4. A multipart email with both parts uses `text/plain`, not the HTML.
5. A WhatsApp export yields conversation windows, not one chunk per message, with
   participants in `meta`.
6. A text file matching no known chat format is rejected with a message that says so.
7. An Aadhaar number in an `.eml` body is masked before storage, as for every other path.
8. `SEARCH_FANOUT` is re-measured with the calendar ingested, and the new number recorded
   beside the constant.
9. The `.ics`, `.eml` and `.txt` in `data/corpus/` all ingest without error.

## Checks to run

```
cd apps/api && uv run pytest && uv run ruff check . && uv run alembic upgrade head
cd apps/api && uv run python -m memora.eval.inspect
pnpm gen:types && pnpm -C packages/core typecheck
```

## How to verify

Ingest the real calendar and search for an event by description rather than by name:

```
curl -X POST http://localhost:8000/search -H "Content-Type: application/json" \
  -d '{"query":"when did I plan to fill the scholarship form"}'
```

Expect the calendar at rank 1 with the matching event as the snippet. Then confirm the
chunk count and that `occurred_at` is populated:

```
docker exec memora-db psql -U memora -d memora -tAc \
  "SELECT count(*), count(occurred_at) FROM chunks WHERE page IS NULL"
```

## Risks

**The fanout question is the real risk**, not the parsing. Ingesting a calendar changes
the shape of the corpus by an order of magnitude, and every retrieval number measured
before it is measured on a different system. Re-measuring is part of this phase.

**Two near-empty calendars and a zip** are in `data/corpus/` — `Birthdays` has 3 events,
`Family` has 1, and `yashvarpe2005@gmail.com.ical.zip` is a duplicate of the extracted
folder that no reader handles. Worth deleting the zip before the gold set references it.

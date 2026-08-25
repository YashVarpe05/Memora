# Phase 3d — the format a thing arrives in is not what it is

**Predictions recorded before the prompt is changed.** Nothing here was written after
seeing a result.

> **Status 2026-08-25, 23:50 IST.**
> **Step 1 ran and HELD completely** — see `docs/PHASE3C-NOSKIP.md`. All 21 rows identical
> with stage 1 forced on. The skip costs nothing measurable.
> **Step 2 is applied but UNMEASURED.** The prompt sentence is in
> `services/query_understanding.py`; the run failed on all 13 calls with
> `RESOURCE_EXHAUSTED` and the harness refused to write it. **Do not trust or demo the
> extractor until `docs/PHASE3D.md` exists.**
>
> The budget arithmetic in this file was right about the order and wrong about the total.
> Step 1 cost 5 as predicted, but the day already carried 16 calls from measuring phase 3c,
> so 5 + 13 was never available *today* — the plan costed the two steps against a fresh
> ceiling and the ceiling was not fresh. **A day's remaining budget is not the day's budget,
> and this plan did not distinguish them.** Step 2 needs a full 13 on a clean day.

## The finding this fixes

`PHASE3C.md` located the whole 0.947 → 0.842 regression in two rows, and both have the same
cause. q010 and q012 expect a **WhatsApp screenshot**; stage 1 gave both a `source_types`
filter with no `image` in it:

| row | rank | extraction | expected file |
|---|---|---|---|
| q010 | 5 | `source_types: [email, pdf]`, `entities: [tcs]` | `WhatsApp Image …01.24.47 (1).jpeg` |
| q012 | 3 | `source_types: [chat, email, pdf]`, `sender: Wajeed` | `WhatsApp Image …01.24.48.jpeg` |

The queries say "on email" and "the message wajeed sent". The documents are **photographs of
those messages**. Stage 1 read the *subject* of the query as the *format* of the file.

The prompt already covers the inverse — "a scanned or printed email saved as a file is `pdf`,
not `email`" — and not this. **The fix is one sentence, and it is the mirror of a sentence
already there.**

### Why this is a report finding and not a corpus quirk

**In a personal archive the format a thing arrives in almost never matches what it is.** A
WhatsApp screenshot of an email is an image. A scanned receipt is a PDF. A forwarded job
posting is a photograph of somebody else's screen. Filtering on inferred format is
structurally fragile, and soft filters bound that damage without removing it — q008 survives
the same wrong filter at 0.670 similarity while q010 dies of it at 0.528.

That generalises past this corpus, which is why the fix is a prompt sentence rather than a
special case for two rows.

## The budget, settled before running rather than discovered mid-run

The cache keys on model **and prompt**, so changing the prompt invalidates every entry.
Counted directly rather than estimated:

| step | calls | why |
|---|---|---|
| **1. no-skip falsifier**, current prompt | **5** | 16 of 21 rows are already cached for `gemini-2.5-flash`. Only q002, q003, q004, q020, q021 are cold. |
| **2. prompt fix**, full run with skip on | **13** | the prompt change invalidates all 21; 8 are skipped, so 13 are cold |
| | **18 of 20** | fits, with two to spare |

**They fit — but only in this order, and only because of an accident.** Today's three-call
harm probe cached q005, q011 and q015 as a side effect, which is why step 1 costs 5 instead
of 8. Without that it would be 8 + 13 = 21 and one of them would have to wait.

**Order is not negotiable.** Step 1 must run against the *current* prompt or its numbers are
not comparable to `PHASE3C.md`, and step 2 destroys that prompt's cache. Running them the
other way round silently measures two different systems.

**If step 1 costs more than 5 calls, stop and recount before step 2.** That means the cache
is not in the state this plan assumes, and 18 was the wrong number.

## Step 1 — the falsifier for keeping the skip

`PHASE3C.md` kept the skip against the pre-agreed rule, on the evidence that no skipped row
lost anything. This is the test of that claim.

```
cd apps/api && STAGE1_CACHE=true uv run python -m memora.eval.baseline --no-stage1-skip --out docs/PHASE3C-NOSKIP.md
```

There is no `--no-stage1-skip` flag yet. It has to be added — a flag that forces stage 1 on
every row, distinct from `--no-stage1` which turns it off entirely.

| prediction | what it would mean |
|---|---|
| **q005, q011, q015 all stay rank 1** | **HELD** — the skip cost nothing, and keeping it stands |
| any of the three ranks above 1 | **BROKEN** — the skip cost that row, and it gets reverted |
| Recall@1 stays 0.842 | expected: the two losses are q010 and q012, which run stage 1 in both arms |
| Recall@1 rises above 0.842 | the skip cost something after all |

**Highest confidence: q011 holds.** It was measured at rank 1 today *without* its
`[uipath, chennai]` filter, and adding a filter that matches can only boost it.

**The one thing that would surprise me:** q005 or q015 moving. The pinned model returns *no
filter at all* for both, so the no-skip arm should be byte-identical to the skip arm for
them. If either moves, the skip is not the only difference between the arms and something
in the harness is not what it claims to be.

## Step 2 — the prompt sentence

Added to `SYSTEM_PROMPT`, beside the existing scanned-email line:

> A photograph or screenshot of a message, email, or document is an `image`, whatever the
> content shows. Judge the format of the file, not the subject of the query.

### Predictions

| row | now | predicted after | reasoning |
|---|---|---|---|
| **q010** | rank 5, `[email, pdf]` | **rank 1**, includes `image` | the target is a jpeg; today's filter demotes it and it is the lowest-similarity row in the set at 0.528, so it has the most to gain |
| **q012** | rank 3, `[chat, email, pdf]` | **rank 1**, includes `image` | same mechanism at 0.567 |
| **q008** | rank 1, `[chat]` | **rank 1, and the extraction gains `image`** | the row that pins the diagnosis |
| **q013** | rank 1, `[chat]` | rank 1, extraction gains `image` | also a WhatsApp jpeg; already survives, should get more margin |
| q001, q007 | rank 1, `[image]` | unchanged | already correct; the sentence must not disturb them |
| q009 | rank 1, no `source_types` | unchanged | no format named in the query |
| q014, q016, q017, q018 | rank 1 | unchanged | calendar and date rows, no photograph involved |
| q019 | miss | **miss** — the control | its file is not indexed. If it stops missing, something other than the prompt changed |
| skipped rows | unchanged | **unchanged, guaranteed** | q002, q003, q004, q005, q011, q015, q020, q021 never reach stage 1, so the prompt cannot touch them |
| **Recall@1** | 0.842 | **0.947 (18/19)** | q010 and q012 recovering is the entire delta |

### q008 is the load-bearing prediction

It receives the same wrong filter as q010 and q012 today and holds rank 1 anyway. So:

- **q008 stays rank 1 and its extraction gains `image`** → the diagnosis is confirmed. The
  filter was wrong for all three; only similarity decided who survived.
- **q008 moves** → the diagnosis is wrong. Its rank does not depend on the filter today, so
  a change in its rank means the prompt edit changed something other than the format axis —
  most likely it perturbed `semantic_query`, and `PHASE3.md` already records what that costs
  (q007, rank 2 → 4, from a rewrite rather than a filter).

**A rank change in q008 is a bigger result than q010 recovering**, because it would mean a
prompt edit aimed at one axis moved another.

### The mirror risk

The new sentence pushes toward `image`. The risk is that it over-applies and starts calling
genuine PDFs images:

| row | risk | why |
|---|---|---|
| **q006** "the mail yash sent to rutuja" | **highest** | the answer is `mail.pdf`, a real PDF. Today the existing scanned-email line correctly yields `[email, pdf]`. If the new sentence overrides it and returns `image`, **the fix breaks the row the original sentence was written to protect** |
| q005 | none | skipped, never reaches stage 1 |

**If q006 regresses, the sentence is wrong and reverts.** The two rules must compose, not
compete: printed-and-scanned → `pdf`, photographed-on-a-screen → `image`. If one prompt
cannot hold both distinctions, that is the finding, and it is a more interesting one than
the fix working.

## Acceptance

1. Step 1 runs before any prompt edit, and costs 5 calls. Recount if not.
2. `--no-stage1-skip` forces stage 1 on every row and is distinguishable in the report from
   both a skip and a failure.
3. Every row above marked held or broken by id, not in aggregate.
4. q006 checked explicitly and by name, not inferred from the headline.
5. Total spend ≤ 18 of 20, with the count reported.

## What waits

Nothing, if the count holds. **Refusal (`phase-3b`) still waits** — it needs its own cold 13
after its own prompt change, and there is no day that fits 5 + 13 + 13. The labelling half is
already built and costs nothing; only the measurement is blocked.

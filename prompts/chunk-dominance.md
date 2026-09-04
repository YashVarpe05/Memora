# Rank-1 loss for text-free documents — diagnosis, options, predictions

Written before implementing. Predictions are pre-registered so they can be wrong.

## The brief, and where it needs correcting

The task was framed as chunk dominance: scoring takes the best chunk per document, so a
353-chunk calendar has 353 draws against a 1-chunk ID card's one, and corpus share acts as
relevance. That mechanism is real and is measured below. **It is not the proximate cause of
either Recall@1 miss**, and a chunk normalisation on its own would not move them.

## What the numbers say

Corpus (eval owner, 15 documents, 377 chunks):

| document | chunks | CLIP |
|---|---|---|
| `yashvarpe2005@gmail.com.ics` | **353** | 0 |
| four PDFs | 3–5 each | 0 |
| `Birthdays_….ics` | 3 | 0 |
| five WhatsApp images | 1 each | 1 each |
| `college_id.jpg`, `DSC02946.JPG`, 2 others | **0** | 1 each |

One document holds **93.6%** of all chunks. Nine of fifteen documents have 0 or 1 chunk.

Both Recall@1 misses at 0.900 are the same shape:

| row | expects | chunks in it | got | rank 1 was |
|---|---|---|---|---|
| q019 `visual_recall` | `DSC02946.JPG` | **0** | rank 2, score 0.0164 | `…gmail.com.ics` 0.5540 |
| q024 `document_identity` | `college_id.jpg` | **0** | rank 2, score 0.0164 | `…gmail.com.ics` 0.6152 |

`0.0164` is not a similarity. It is `1/(60+1)` — the RRF score for a document appearing at
rank 1 of exactly one list.

## The actual mechanism

`fusion.reciprocal_rank_fusion` scores `1/(k + rank)` per list, k=60. A `.ics` file has no
CLIP embedding, so it cannot appear in the image list; a 0-chunk image cannot appear in the
text list. So for both failing rows:

- calendar: text rank 1, image absent → **1/61**
- the wanted image: text absent, image rank 1 → **1/61**

**An exact tie.** `sorted(..., reverse=True)` is stable, and `fuse_results` merges the text
side first, so the text document keeps the earlier position and wins. The tie-break is an
artifact of insertion order, not a decision anyone made.

This generalises to a structural property:

> A document found only by the image index can never rank 1 while any document is found by
> the text index. Best case it ties, and it always loses the tie.

That is why the flagship row fails, and it would fail identically with a 3-chunk calendar.

Two consequences worth stating separately:

1. **Chunk dominance is real but upstream.** It is why the calendar reaches text rank 1 for
   "my college ID card" at all — 353 chances to produce one chunk mentioning "college".
   Fixing it changes *which* text document takes rank 1, not that a text document does.
2. **The filter bonus cannot reach these documents.** `fuse_results` gives an image-only
   document `score = doc.score` (the RRF value) with no boosts applied, so stage 1
   correctly extracting `document_type: id_card` buys `college_id.jpg` nothing. The one
   signal that most directly identifies an ID card is computed and then discarded.

## Options

### A. Normalise the text score by chunk count
`score / (1 + α·log n)`, or mean-of-top-k over available chunks.

Addresses the real upstream bias, and the docstring already calls max-per-document "a knob
the baseline will test, not a truth". **But it does not fix either failing row**, and it has
a measured, specific harm: four gold rows legitimately expect the 353-chunk calendar, and
q016's margin over `mail.pdf` is **0.0088** (0.6025 vs 0.5937). Any penalty above ~1.5% on
the calendar loses q016. Mean-of-top-k is worse here — q014/q015/q016/q018 are each answered
by *one* event buried in 353 chunks, which is exactly the single-decisive-chunk case
averaging destroys.

### B. Weight the image list when text evidence is weak
The text gate already decides whether to consult CLIP at all, and only consults it when text
evidence is weak. That decision is evidence: if the gate fired, the text list is known to be
poor. Give image contributions `w/(k + rank)` with `w > 1` in that case, so an image rank-1
beats a text rank-1 precisely when text was already judged inadequate.

Principled — it reuses a judgement already made rather than inventing a constant — but `w`
is a new tunable, and it changes ordering for every fused query, not only the broken ones.

### C. Make the tie-break a decision instead of an accident
On an exact RRF tie, prefer the document the *type filter* agrees with, then the one from
the modality the gate trusts. Minimal, deterministic, and it converts an insertion-order
artifact into a stated policy. Also the natural home for fixing consequence (2): let a
`document_type` match count for image-only documents.

Narrow: it only touches exact ties. That is also its virtue — nothing else moves.

## What I would do, and why

**C first, then A, measured separately.**

C, because it is the smallest change that addresses the measured cause, it cannot move a row
that is not tied, and it fixes the discarded-`document_type` defect on the way. B invents a
weight to solve a problem C solves with a signal already computed. A is worth doing on its
own merits — corpus share should not act as relevance — but it is a *different* finding and
must not be smuggled into the same row of the table, or the ablation cannot attribute
either result.

## Predictions, pre-registered

**Under C (tie-break by type agreement, then gate-trusted modality):**

- **q024 → rank 1.** `college_id.jpg` has `document_type: id_card`; the query asks for an ID
  card. The tie resolves on the one signal that actually identifies the document.
- **q019 → stays rank 2.** `DSC02946.JPG` has **no** `document_type` and the query ("photo
  of me leaning on the balcony at college") requests none, so type agreement cannot break
  that tie. It should fall to the modality rule — and I am genuinely unsure it will, because
  the gate's own decision may not be recorded by the time fusion runs. **If q019 moves, my
  model of the gate is wrong.**
- **Recall@1 0.900 → 0.950** (19/20) if only q024 moves; 1.000 if q019 moves too.
- **Nothing else moves.** No other row is decided by an exact tie. If a third row changes,
  C is touching more than ties and the implementation is wrong.
- **Refusal stays 0.500.** q022/q023 are answered because CLIP always returns a nearest
  neighbour; a tie-break does not add a threshold.

**Under A (chunk normalisation, measured after C):**

- **q016 regresses.** 0.0088 margin. This is the harm, and it is the reason to measure A
  separately rather than shipping it because the headline number improved.
- q014/q015/q018 survive a modest penalty (margins 0.261, 0.143, 0.125).
- q024/q019 unchanged by A alone — already argued.
- So A most likely **lowers** Recall@1 while fixing a real bias. That is a legitimate result
  and the ablation table should show it rather than hide it.

## Also to be written

**q025**, isolating the visual path: a wording sharing no tokens with `college_id.jpg`, so
filename and `document_type` are not live routes and only CLIP can answer. Added alongside
q024, never by weakening it.

## Falsifiers

- If q024 does not reach rank 1 under C, the tie-break is not the mechanism and this whole
  diagnosis is wrong.
- If more than the predicted rows move, C is not confined to ties.
- If A does not regress q016, the 0.0088 margin was measured wrong.

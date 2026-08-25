# The quota ceiling — what paying actually costs

**Decision document. No implementation, no quota spent to produce it.** Token counts are
measured from this repo; prices are list prices fetched 2026-08-26.

## The answer first

**About ₹21 a month at 30 searches a day. About ₹2.30 for a demo.** The entire project's
stage 1 usage since it began is under ₹5.

**The ceiling that has shaped four phases of this project is worth roughly one cup of tea
per month.** That is the whole finding, and everything below is the arithmetic behind it.

## Measured, not estimated

Counted from `SYSTEM_PROMPT` and from the 39 real extractions in
`data/eval-runs/stage1-cache.json` — these are the actual bytes sent and returned:

| | tokens |
|---|---|
| system prompt | **396** |
| user query (median across the 21 gold rows) | **21** (range 14–24) |
| **input per call** | **~417** |
| output, real extractions (median) | **47** (range 40–58) |

Gemini 2.5 Flash paid tier: **$0.30 per 1M input tokens, $2.50 per 1M output.**
At ₹95.7/USD:

```
input   417 × $0.30/1M  = $0.000125
output   47 × $2.50/1M  = $0.000118
                          ---------
per search              = $0.000243  ≈ ₹0.023
```

**₹0.023 per search. About 43 searches per rupee.**

| what | calls | cost |
|---|---|---|
| one cold gold-set eval (with the skip) | 13 | **₹0.30** |
| one cold eval without the skip | 21 | ₹0.48 |
| a defence demo plus two rehearsals | ~100 | **₹2.30** |
| 20 searches/day for a month — today's ceiling | 600 | ₹14 |
| **30 searches/day for a month — realistic personal use** | 900 | **₹21** |
| 100 searches/day for a month — implausible for one user | 3,000 | ₹70 |

**Accuracy caveat.** Token counts use `tiktoken` (a GPT tokenizer) because Gemini's is not
available offline. Expect ±20%. At 2× the figure is ₹42/month, which does not change any
decision — that is why the caveat is stated rather than resolved.

## One correction to the framing

**Embeddings do not stay free.** Moving to the paid tier bills them too: `gemini-embedding-001`
is **$0.15 per 1M input tokens**, with no free allowance on a billed project. The good news
is that it is still nothing:

| what | tokens | cost |
|---|---|---|
| one query embedding | ~20 | ₹0.0003 |
| a full 377-chunk corpus re-ingest | ~170,000 | **₹2.45** |

Re-ingesting the entire corpus costs about the same as one demo. The 1000/day embedding
ceiling has never been the binding constraint and paying removes it too.

**What genuinely stays free:** CLIP (local, no API), Tesseract OCR (local, in a container),
and everything in Postgres. Those are free because they run on the machine, not because of
a tier.

## The argument that is not about money

This is the part that matters more than the rupees.

**Google's free tier terms and its paid tier terms differ on human review.**

- **Unpaid:** "Google uses the content you submit to the Services and any generated
  responses to provide, improve, and develop Google products and services," and "human
  reviewers may read, annotate, and process your API input and output."
- **Paid:** "Google doesn't use your prompts … or responses to improve our products."
  Logging is limited to abuse detection and legal compliance.

Now recall what stage 1 actually sends. Architectural rule 1 in `PRODUCT.md` is strict —
**no document content ever reaches the model, only the user's own query text.** That rule
has been enforced and tested. But the query text *is* the personal part:

> "my college fee receipt" · "the mail yash sent to rutuja" · "find my Aadhaar card"

**On the free tier, a human reviewer at Google may read those.** Not the documents — rule 1
holds — but the questions, which name the user's documents, correspondents and intentions.

A project whose central claim is privacy is currently running its one outbound call on the
tier whose terms permit human review of exactly the string that carries the personal
information. **Paying is a privacy improvement, not just a throughput one**, and it is
strange to have arrived at that conclusion by pricing a quota.

This belongs in the report either way. If the paid tier is not taken, the limitation has to
be stated: *"query text is sent to a third party under terms permitting human review."*
That sentence is worth ₹21 a month to delete.

## What this settles for the phases after it

The 20/day ceiling has shaped four phases:

- **Option C (the skip)** was chosen to raise 20 → ~25 searches a day. Measured in
  `PHASE3C-NOSKIP.md` as costing nothing, so it stays — but its justification is now
  **reproducibility only**, and paying removes even that. It is no longer load-bearing.
- **Refusal (`phase-3b`)** was designed around spending zero extra calls, and the plan says
  so explicitly. That constraint was real and is now gone. A design that needs a second call
  is still worth avoiding for *latency*, but no longer for budget.
- **Model choice.** `gemini-flash-lite-latest` was tried purely to dodge the quota and
  measured at Recall@1 0.789, below the dense-only baseline. That workaround has no reason
  to exist now.
- **The eval loop.** Cache warming, two-day cold runs, "which measurement waits" — all of it
  is quota bookkeeping. At ₹0.30 a run, an eval can be run on demand.

## Recommendation

**Take the paid tier.** The money is not the cost; a card on file is. Against that:

1. It removes a ceiling that makes the product undemoable — 20 searches a day is not an app,
   and a mid-demo silent degradation is a live risk the banner mitigates but does not fix.
2. It is a **privacy improvement**, which this project's whole thesis rests on.
3. It deletes an entire category of work — quota planning — that has consumed real time in
   the last several sessions and produces no product.

**If the answer is no**, that is a legitimate call and the consequences should be written
down rather than absorbed: the throughput limit goes in the report as a stated constraint,
the human-review sentence goes in the limitations section, and the option-E local model for
stage 1 comes back onto the table — with `PHASE3.md`'s warning attached, that a weaker
extractor measured *below* using no extractor at all.

## Not decided here

Whether the ID card, the corpus, or any document ever goes to a hosted model. It does not,
and paying does not change that. Rule 1 is architectural, not economic.

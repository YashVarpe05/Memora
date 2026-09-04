# Rules-only stage 1 — how much of query understanding needs a model?

Pre-registered. Written before the extractor exists, so the predictions can be wrong.

## Why this decides the on-device build

Every other component ports to a phone: ML Kit for OCR, ONNX for CLIP, SQLite for storage.
**Stage 1 is the only piece that currently needs a 3B language model.** If rules can do the
extraction, the on-device build needs no LLM at all — which changes its size, its battery
cost, and whether it runs on a mid-range phone. Better to know now than at week seven.

Half of it is already done and already measured. `document_type` is extracted from the query
by `document_type.classify()` — the *same vocabulary that types the documents* — and that
change is what moved q024 to rank 1. **That field is rules-only today**, and it works, and
it replaced a model output that was always `None`. This experiment asks whether the rest
follows.

## Bars

| arm | Recall@1 |
|---|---|
| dense-only | 0.842 |
| local `qwen2.5:3b` stage 1 | **0.950** |

## What the fields are worth

Only four extracted fields reach ranking, via `boosted_score`:

- `source_types` — ±FILTER_BONUS. **The only one that can be negative**, so the only one a
  wrong guess actively harms.
- `document_type` — +FILTER_BONUS, rewarded never penalised. Already rules-only.
- `sender` — +FILTER_BONUS on a substring match either way.
- `after` / `before` — need `occurred_at`, so only calendar rows can use them.

`semantic_query`, `entities` and `needs_time_resolution` do not change ranking today.

## Row-by-row prediction

Judged on lexical signal alone against the existing `SOURCE_WORDS`, `_SENDER` and
`VOCABULARY` tables.

**Rules extract the same useful signal as the model (10 rows):**

| row | signal | from |
|---|---|---|
| q001 | `photo` → image | SOURCE_WORDS |
| q006 | `mail` → email, `yash sent` → sender | both |
| q007 | `screenshot` → image | SOURCE_WORDS |
| q008 | `whatsapp` → chat | SOURCE_WORDS |
| q012 | `message` → chat, `wajeed sent` → sender | both |
| q013 | `whatsapp message` → chat, `from aradhana` → sender | both |
| q017 | `reminders` → calendar | SOURCE_WORDS |
| q018 | `calendar` → calendar | SOURCE_WORDS |
| q019 | `photo` → image | SOURCE_WORDS |
| q024 | `ID card` → id_card | VOCABULARY (already shipped) |

**Rules extract nothing; the arm degenerates to dense-only for these (7 rows):**
q002, q003, q004, q005, q011, q015, q025.

This is not automatically a loss. Dense-only already scores 0.842, so most rows pass without
any filter — **the question is only whether these are rows stage 1 currently rescues.**
q025 is deliberately in this set: it was written to have no lexical route at all.

**Partial or risky (4 rows):**

- **q010 "the tcs job where they asked to send cv on email" — the predicted regression.**
  `email` is in SOURCE_WORDS, but the expected document is a **WhatsApp image**. `email` is
  a noun *inside the message*, not the medium it arrived by. Rules would set
  `source_types=(email,)` and the correct answer would take **−FILTER_BONUS**. This is the
  one field that can be negative, and this is exactly the case it punishes. A model reading
  the sentence can tell the difference; a word-set cannot.
- **q009 "the job thing anu priya sent"** — `_SENDER` matches `\w+\s+sent`, capturing
  `priya` and losing `anu`. Substring matching should still hit, so degraded not broken.
- **q014 "when was i supposed to fill the scholarship form"** — `when` marks it temporal but
  rules cannot infer *calendar* from "supposed to". The model can. However dense already
  ranks that calendar first at 0.7644, so I expect it to pass anyway.
- **q016 "what i had planned to learn last year"** — `last year` is resolvable to a concrete
  range deterministically, which is strictly better than what the model does with it. But
  q016's margin over `mail.pdf` is **0.0088**, so this row is fragile to any change at all.

## Predictions

1. **Rules land at 0.85–0.95, closer to the model than to dense-only.** Most of the model's
   lift comes from lexically explicit cues — "photo", "whatsapp", "from aradhana" — and a
   word-set captures those exactly. My point estimate is **0.905** (19/21), losing q010 and
   one other.
2. **q010 regresses**, or fails in both arms. If it passes under rules, `email` is not
   reaching `source_types` and my model of the extractor is wrong.
3. **q024 passes under rules** — it already does, by this mechanism.
4. **q025 fails under every arm.** It has no lexical route by construction and the rank-1
   cap is unfixed.
5. **The refusal rate is unchanged at 0.500.** Refusal is decided on raw similarity and
   document-type agreement, and both are already rules-driven.
6. **Latency drops from seconds to microseconds**, and the failure rate to zero — a table
   lookup has no quota, no transport and no parse step. If the rules arm shows any stage-1
   failure, the harness is mislabelling the arm.

## The decision this feeds

- **Rules ≥ 0.93** → the on-device build ships without an LLM. ROADMAP should say so.
- **Rules ≈ 0.842** → the model is buying the entire gap, and that is worth reporting as
  precisely as the alternative.
- **Anywhere between** → the interesting result: report which specific rows need a model,
  because that names what a phone gives up rather than guessing at it.

## Falsifiers

- If rules beat the model, one of the two arms is not running what its label says.
- If q010 passes under rules, `source_types` is not being applied as I have described.
- If the rules arm reports any stage-1 failure, it is not running rules.

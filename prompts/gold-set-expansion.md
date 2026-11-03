# Held-out adversarial gold set — plan (NOT approved)

Pre-registered. Written before any row exists, so the predictions can be wrong.

## Why this, and why now

Every headline number comes from 25 rows, written beside the code they test. Three findings
rest on that:

- **Rules-only stage 1 equals the 3B model** (§7.5). A word table is "exactly the artefact
  that fits the queries it was written beside", and RESULTS.md says a larger adversarial set
  is the measurement that would overturn it.
- **Chunk damping was rejected** because α cannot be chosen without fitting the test. Same
  cause: too few rows, one document holding 93.6% of chunks.
- **q025 is one row.** We do not know whether the visual rank-1 cap is one failure or a
  class.

One answerable row is 0.053 of Recall@1 today. This plan buys resolution, not a better
number. **It may well lower the headline, and that is an acceptable outcome.**

## Dev / held-out split

- `docs/GOLD.jsonl` (25 rows) is declared the **dev set**. Rules vocabulary, tie-break and
  thresholds were all shaped beside it. Unchanged.
- New `docs/GOLD-HELDOUT.jsonl` is **held out**: written blind, committed with predictions
  *before* the first run, run once per arm, never tuned against.
- After the run it is burned. Any change it motivates is re-measured on a fresh set, not on it.

## Decision needed from you (the one question)

The corpus is 14 files, so 40+ new queries over it re-hit the same documents and the three
synopses, three job screenshots and one calendar do most of the work. Two readings:

- **A. Queries only**, current 14 files. No new data; weaker, because the corpus is the
  limiting factor, and the 93.6% skew stays.
- **B. Queries plus ~15 new files** you add (marksheet, receipts, a second PDF set, more
  photos, a second email/chat export, anything real). Much stronger; breaks corpus
  comparability, so it is reported as a new boundary (as §5 did), with dev re-run on the new
  corpus too. Files stay untracked (`test_no_personal_data_tracked`). No synthetic documents
  unless you want them, and they would be labelled synthetic in the results.

**Recommendation: B**, with A as the fallback if files are unavailable.

## Independence: who writes the queries

A set I write alone from the same files is not independent of me. So:

- **You write ~20 queries first**, from memory, the way you would actually ask, without
  opening the files or the vocabulary tables.
- **I write ~25–35 adversarial rows** from the corpus content only, without opening
  `document_type.py`, `rules_query_understanding.py` or `query_signal.py` while writing.
- Target: ~40 answerable + ~15 absence rows. One answerable row ≈ 0.025.

## Adversarial categories (each row tagged)

| tag | what it attacks | example shape |
|---|---|---|
| `paraphrase` | zero token overlap with file name and text | q025-style descriptions |
| `wrong_signal` | query carries a source/type word that points away from the answer | "the email about X" when the answer is a WhatsApp image |
| `near_dup` | three near-identical files, only a detail separates them | synopses, job screenshots |
| `noisy` | typos, Hinglish, transliteration, one-word queries | |
| `temporal` | relative dates against dated files | "two months ago", "this semester" |
| `calendar_trap` | query that must NOT land on the 353-chunk calendar, and ones that should | dominance |
| `visual_only` | descriptions only CLIP can answer, several per image | sizes the rank-1 cap |
| `absent_typed` | names a type the corpus lacks | "my 12th marksheet" |
| `absent_untyped` | absent, names no type (visual absence, near-miss of an existing item) | "photo at the beach" |
| `absent_near_miss` | absent but close to a real file | existing event, wrong year |

Rows also carry `notes` stating why the row is hard and what a pass would and would not prove
(the existing rows set that standard).

## Predictions (ranges, written before any run; finalised at commit time)

Arms: dense-only, rules, local `qwen2.5:3b`. Hosted excluded (not reproducible).

1. **Rules Recall@1 on held-out answerable rows: 0.65–0.80**, below dev's 0.905. Falsifier:
   ≥ 0.88 means the overfitting worry is not supported on this corpus.
2. **Rules vs `qwen2.5:3b` within ±3 rows.** Falsifier: a gap of ≥ 4 rows reopens "ship
   on-device without an LLM".
3. **`wrong_signal`: fails exactly where the dense margin over the runner-up is below
   FILTER_BONUS (0.08).** Predict the quantity, not the direction (§8.7). I will record each
   row's margin before the run.
4. **`visual_only`: at least 75% sit at rank 2** (the tie cap), unless a type opinion breaks
   the tie.
5. **Refusal: `absent_typed` ≥ 0.9, `absent_untyped` ≈ 0.0**, zero false refusals on present
   typed rows. Falsifier for the ceiling story: any `absent_untyped` row refused.
6. **`calendar_trap`: at least one failure attributable to chunk share**, not similarity.

## Steps

1. You answer the A/B question; if B, add files to `data/corpus/` and re-ingest (check
   `docker compose ps` first; DB tests skip silently when containers are down).
2. Freeze: record the commit and the dev run on the (possibly new) corpus as the dev baseline.
3. You write your ~20 queries; I write mine. `python -m memora.eval.retrieval
   docs/GOLD-HELDOUT.jsonl` validates schema and that every `expected_sources` file exists.
4. Commit gold file + finalised predictions. **Nothing runs before this commit.**
5. Run each arm once; archive to `data/eval-runs/`. Read the skip count, not the exit code.
6. Report per tag, counts first, in a new RESULTS.md section: prediction vs outcome per item,
   including the wrong ones, and the corpus-boundary note if B.
7. Declare held-out burned. No retrieval changes in this task.

## Out of scope

No tuning, no BM25, no fusion change, no new harness features or CI tooling (per-tag tallies
by hand from the run file if the harness does not print them), no hosted-model runs.

## Cost

Qwen arm ~4.6 s/query, ~5 min for the set; rules and dense-only seconds. No quota spent.
Your time is the real cost: ~20 queries, and ~15 files under B.

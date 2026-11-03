# Research-informed next steps (PLAN, not approved)

Written 2026-10-22. Sources were read as abstracts and search snippets, not full papers.
Treat every "the paper says" below as a pointer to verify before it justifies a change.

## Where the project stands

Recall@1 0.905 / Recall@5 1.000 / MRR@10 0.952 / refusal 0.500 on 25 gold rows, 14 documents.
Stage 1 is rules-only. Open, documented gaps:

1. **q025 fails**: purely visual retrieval is capped at rank 2 (RRF tie, 1/61 each).
2. **Visual absence unsolved**: q022/q023 are answered, not refused; CLIP ranks everything.
3. **BM25 is specified (PRODUCT.md, CLAUDE.md) but not built.** Code is dense + soft filters; RRF fuses text with CLIP only.
4. **One document holds 93.6% of chunks**; chunk damping was rejected on this corpus.
5. **25 rows is small**; a larger adversarial set is what could overturn the rules-only result.

## What the literature says about each

| gap | finding | source | caveat |
|---|---|---|---|
| 1, 2 | Raw CLIP cosine is a compressed, uncalibrated ranking signal; normalising each image's score against auxiliary reference prompts (BSAP) corrects a bias toward high-scoring candidates | arXiv 2402.18400 | evaluated on referring-expression comprehension, not file search or absence |
| 1 | Convex combination of normalised scores beat RRF in- and out-of-domain, tunes with few labelled examples; RRF is sensitive to k | arXiv 2210.11934 (Bruch et al.) | lexical + dense, not cross-modal; our gold set is tiny, so a tuned weight risks fitting the test |
| 2 | Abstention can be driven by score-distribution features of the ANN result list (concentration, query length), no extra LLM call | arXiv 2609.22056 | multi-hop text QA; needs labelled data we do not have |
| 4 | MaxP is usually the best passage aggregation but over-weights one passage; no source found measuring chunk-count inflation | survey arXiv 2509.07759 | gap in literature; our measurement may be the contribution |
| 3 | Personal/lifelog systems are image- and sensor-centric, use CLIP/BLIP plus an LLM for query parsing and report retrieval as the bottleneck | NTCIR/LSC lifelog papers (DCU) | none targets on-device personal documents; closest framing paper arXiv 2606.29652 |

## Options (pick one; each needs a pre-registered prediction first)

- **A. Build BM25** (Postgres full-text `ts_rank_cd` is not true BM25; say so, or use a real BM25 implementation). Closes the gap between the spec and the code. Baseline = current committed run. Lowest risk.
- **B. Fusion ablation for q025**: RRF-with-gate (current) vs per-list min-max convex combination, with and without CLIP reference-query normalisation. Report all arms. Risk: weight tuning on 25 rows is fitting the test, and ROADMAP says retrieval tuning is finished, so this is only justified because q025 is a known failing row.
- **C. Larger adversarial gold set** (the measurement that could overturn rules-only stage 1, and the only honest way to choose a damping or fusion weight).
- **D. Skip retrieval**: auth (phase 5), then report and UML, per ROADMAP.

## Recommendation

C first, then A, then B only if C gives enough rows to avoid fitting. D is the roadmap order if retrieval work is to stop.

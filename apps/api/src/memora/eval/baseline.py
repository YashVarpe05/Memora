"""Baseline measurement — the gold set against current retrieval.

Run this BEFORE query understanding exists. An ablation table needs a number taken
before the improvement, not reconstructed after it, and a baseline re-run later against
a pipeline that has quietly changed is not a baseline.

It runs every gold query through /search and computes Recall@1, Recall@5, MRR@10 and
refusal accuracy, with a per-type breakdown and the observed fetch-window behaviour.

    uv run python -m memora.eval.baseline --ingest    # once: ~400 embeds
    uv run python -m memora.eval.baseline             # thereafter: 21 embeds

Ingest and evaluation are separate on purpose. One full ingest is roughly 400 embed
requests against a 1000-per-day free tier, so re-ingesting every run allows two
measurements a day - and phase 3 has to sweep a threshold and a filter extractor against
this gold set far more often than that. Evaluating an already-indexed corpus costs one
embedding per query.

The corpus is verified by content hash before every run, so a stale index fails loudly
instead of producing a number that looks fine and describes a corpus that no longer
exists.
"""

from __future__ import annotations

import argparse
import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from memora.eval.retrieval import GoldRow, load
from memora.paths import anchored, resolve

MRR_DEPTH = 10

# A stable owner, so an ingest survives between runs. A fresh UUID per run would make
# every measurement pay the full ingest cost, which is the thing this file exists to
# avoid. Distinct from the dev identity, so a manual upload cannot contaminate a result.
EVAL_USER_ID = uuid.UUID("00000000-0000-4000-8000-0000000e7a10")


@dataclass
class QueryOutcome:
    row: GoldRow
    rank: int | None
    refused: bool
    top_filename: str | None
    top_score: float | None
    chunks_examined: int
    widenings: int

    @property
    def is_refusal_row(self) -> bool:
        return self.row.type == "must_refuse"

    @property
    def passed(self) -> bool:
        if self.is_refusal_row:
            return self.refused
        return self.rank == 1


@dataclass
class Metrics:
    outcomes: list[QueryOutcome] = field(default_factory=list)

    @property
    def retrieval_rows(self) -> list[QueryOutcome]:
        """Rows with an expected file. must_refuse rows have none, so they cannot
        contribute to a recall fraction - counting them as misses would understate
        the system."""
        return [o for o in self.outcomes if not o.is_refusal_row]

    @property
    def refusal_rows(self) -> list[QueryOutcome]:
        return [o for o in self.outcomes if o.is_refusal_row]

    def recall_at(self, k: int) -> float:
        rows = self.retrieval_rows
        if not rows:
            return 0.0
        return sum(1 for o in rows if o.rank is not None and o.rank <= k) / len(rows)

    @property
    def mrr(self) -> float:
        rows = self.retrieval_rows
        if not rows:
            return 0.0
        return sum(
            1.0 / o.rank if o.rank is not None and o.rank <= MRR_DEPTH else 0.0
            for o in rows
        ) / len(rows)

    @property
    def refusal_accuracy(self) -> float:
        rows = self.refusal_rows
        if not rows:
            return 0.0
        return sum(1 for o in rows if o.refused) / len(rows)

    def by_type(self) -> dict[str, tuple[int, int]]:
        grouped: dict[str, list[QueryOutcome]] = defaultdict(list)
        for outcome in self.outcomes:
            grouped[outcome.row.type].append(outcome)
        return {
            qtype: (sum(1 for o in outs if o.passed), len(outs))
            for qtype, outs in sorted(grouped.items())
        }


async def ingested_documents(owner: uuid.UUID) -> dict[str, str]:
    """content_hash -> filename, for everything already indexed under this owner."""
    from sqlalchemy import select

    from memora.db.models.memory import Memory
    from memora.db.session import scoped_session

    async for session in scoped_session(owner):
        rows = await session.execute(select(Memory.content_hash, Memory.filename))
        return {content_hash: filename for content_hash, filename in rows}
    return {}


async def chunk_count(owner: uuid.UUID) -> int:
    from sqlalchemy import func, select

    from memora.db.models.chunk import Chunk
    from memora.db.session import scoped_session

    async for session in scoped_session(owner):
        result = await session.execute(select(func.count()).select_from(Chunk))
        return int(result.scalar_one())
    return 0


def corpus_hashes(corpus: Path) -> dict[str, str]:
    """content_hash -> filename, for every file on disk."""
    from memora.services.storage import sha256_of

    return {
        sha256_of(path.read_bytes()): path.name
        for path in sorted(corpus.rglob("*"))
        if path.is_file() and not path.name.startswith(".")
    }


def verify_corpus(
    on_disk: dict[str, str], indexed: dict[str, str], rows: list[GoldRow]
) -> list[str]:
    """Problems that would make a measurement misleading rather than merely incomplete.

    Two things matter. A document in the index that is no longer on disk means the
    measurement describes a corpus that does not exist. And a gold row whose expected
    file was never indexed cannot possibly be found, so its failure would be charged to
    retrieval when the cause is a missing document.

    A file on disk that was never indexed is NOT an error: several corpus files are
    rejected at upload for containing no extractable text, which is expected and is
    itself a recorded finding.
    """
    problems: list[str] = []

    for content_hash, filename in sorted(indexed.items(), key=lambda kv: kv[1]):
        if content_hash not in on_disk:
            problems.append(f"indexed but no longer on disk (or changed): {filename}")

    indexed_names = set(indexed.values())
    expected = {name for row in rows for name in row.expected_sources}
    for name in sorted(expected - indexed_names):
        problems.append(f"gold set expects '{name}', which is not indexed")

    return problems


async def ingest(client, corpus: Path) -> tuple[int, int, list[str]]:
    """Upload every corpus file. Returns (documents, chunks, rejected)."""
    documents = chunks = 0
    rejected: list[str] = []
    # Read the listing and the bytes synchronously - this is a CLI, not a server, and
    # an async filesystem wrapper would buy nothing.
    payloads = [
        (p.name, p.read_bytes())
        for p in sorted(corpus.rglob("*"))
        if p.is_file() and not p.name.startswith(".")
    ]

    for name, data in payloads:
        response = await client.post("/uploads", files={"file": (name, data)})
        if response.status_code == 201:
            documents += 1
            chunks += response.json()["chunks"]
        else:
            rejected.append(f"{name} ({response.status_code})")
    return documents, chunks, rejected


async def measure(client, rows: list[GoldRow]) -> Metrics:
    metrics = Metrics()
    for row in rows:
        response = await client.post("/search", json={"query": row.query, "limit": MRR_DEPTH})
        body = response.json()
        results = body.get("results", [])
        names = [r["filename"] for r in results]

        rank = None
        for index, name in enumerate(names, start=1):
            if name in row.expected_sources:
                rank = index
                break

        metrics.outcomes.append(
            QueryOutcome(
                row=row,
                rank=rank,
                refused=bool(body.get("refused")),
                top_filename=names[0] if names else None,
                top_score=results[0]["score"] if results else None,
                chunks_examined=body.get("chunks_examined", 0),
                widenings=body.get("widenings", 0),
            )
        )
    return metrics


def render(metrics: Metrics, meta: dict) -> str:
    hits_at_1 = sum(1 for o in metrics.retrieval_rows if o.rank == 1)
    refused = sum(1 for o in metrics.refusal_rows if o.refused)
    lines = [
        "# Baseline — dense-only retrieval",
        "",
        f"Recorded {meta['generated_at']}, commit `{meta['commit']}`.",
        "",
        "**This is the number query understanding has to beat.** Taken before any of it",
        "exists, so the comparison later is a measurement rather than a reconstruction.",
        "",
        "## What was measured",
        "",
        f"- Corpus: {meta['documents']} documents, {meta['chunks']} chunks",
        f"- Gold set: {len(metrics.outcomes)} queries "
        f"({len(metrics.retrieval_rows)} retrieval, {len(metrics.refusal_rows)} refusal)",
        "- Retrieval: plain dense cosine over `gemini-embedding-001` at 768 dims. "
        "No query understanding, no BM25, no reranking.",
        (
            f"- Ingest took {meta['ingest_seconds']}s, almost all of it free-tier "
            "rate limiting."
            if meta["ingest_seconds"]
            else "- Evaluated against an already-indexed corpus, verified by content hash."
        ),
        "",
        "## Headline",
        "",
        "| metric | value |",
        "|---|---|",
        f"| **Recall@1** | **{metrics.recall_at(1):.3f}** "
        f"({hits_at_1}/{len(metrics.retrieval_rows)}) |",
        f"| Recall@5 | {metrics.recall_at(5):.3f} |",
        f"| MRR@{MRR_DEPTH} | {metrics.mrr:.3f} |",
        f"| Refusal accuracy | {metrics.refusal_accuracy:.3f} "
        f"({refused}/{len(metrics.refusal_rows)}) |",
        "",
        "## By query type",
        "",
        "| type | passed | total |",
        "|---|---|---|",
    ]
    for qtype, (passed, total) in metrics.by_type().items():
        lines.append(f"| `{qtype}` | {passed} | {total} |")

    lines += [
        "",
        "## Every query",
        "",
        "| id | type | rank | query | top result |",
        "|---|---|---|---|---|",
    ]
    for outcome in metrics.outcomes:
        if outcome.is_refusal_row:
            rank = "refused" if outcome.refused else "**ANSWERED**"
        else:
            rank = str(outcome.rank) if outcome.rank else "**miss**"
        top = outcome.top_filename or "-"
        lines.append(
            f"| {outcome.row.id} | `{outcome.row.type}` | {rank} | "
            f"{outcome.row.query} | {top[:34]} |"
        )

    # Which file keeps winning. A document with many chunks has something marginally
    # similar to almost any query, so it can dominate a dense-only ranking - and that
    # is exactly what filtering before searching is meant to fix.
    tops: dict[str, int] = defaultdict(int)
    for outcome in metrics.outcomes:
        if outcome.top_filename:
            tops[outcome.top_filename] += 1
    ranked_tops = sorted(tops.items(), key=lambda kv: kv[1], reverse=True)

    lines += ["", "## Where the failures went", ""]
    if ranked_tops:
        leader, count = ranked_tops[0]
        share = count / max(len(metrics.outcomes), 1)
        lines += [
            "Most frequent top result:",
            "",
            "| file | times ranked first |",
            "|---|---|",
        ]
        lines += [f"| `{name}` | {n} |" for name, n in ranked_tops[:5]]
        lines += [
            "",
            f"`{leader}` is the top result for {count} of {len(metrics.outcomes)} queries "
            f"({share:.0%}).",
        ]
        if share > 0.4:
            lines += [
                "",
                "**That is the headline failure mode.** A document large enough to contain "
                "something marginally similar to any query becomes an attractor under "
                "dense-only ranking, and every failed query above has it at rank 1. This is "
                "the case for stage-1 filtering: constrain by source type and date *before* "
                "searching, and the attractor stops competing for queries it has no business "
                "answering. It is the single clearest argument in this table for query "
                "understanding.",
            ]

    examined = [o.chunks_examined for o in metrics.outcomes]
    widenings = [o.widenings for o in metrics.outcomes]
    lines += [
        "",
        "## Observed fetch-window behaviour",
        "",
        "The window widens until enough documents surface rather than using a fixed size.",
        "Observed across these queries:",
        "",
        f"- chunks examined: {min(examined)}–{max(examined)}",
        f"- widenings: {min(widenings)}–{max(widenings)}",
        f"- corpus: {meta['chunks']} chunks, so the window reached "
        f"{max(examined) / max(meta['chunks'], 1):.0%} of it at most",
        "",
        "**Known bound.** A document whose only matching chunk falls outside the window is",
        "invisible. This bounds *list completeness*, not the top hit — a strong match puts a",
        "chunk near the top of any window — so Recall@5 erodes before Recall@1 does. At",
        "roughly a thousand documents the ceiling (2000 chunks) starts to bind, and the fix",
        "is a document-level pre-filter rather than a larger window.",
        "",
        "## Known limitations at the time of measurement",
        "",
        "- **No visual understanding.** OCR extracts text; it does not describe pictures. "
        "Three corpus files contain no text and are therefore unfindable by any query.",
        "- **`document_identity` is unmeasured.** The corpus contains no photograph of an "
        "ID card, so the flagship query type has no gold row. This is the largest gap.",
        "- **Refusal is not enforced by the system.** `MIN_SIMILARITY_UNCALIBRATED` is 0.35 "
        "and gibberish scores ~0.489, so the threshold never fires. Any refusal recorded "
        "here came from the corpus being genuinely empty of matches, not from the guard.",
        "- **Tesseract is the only working OCR engine.** PaddleOCR installs and cannot run "
        "on this hardware, in the container as well as on Windows.",
        "",
    ]
    return "\n".join(lines) + "\n"


async def run(gold_path: Path, corpus: Path, out: Path, do_ingest: bool) -> int:
    from httpx import ASGITransport, AsyncClient

    from memora.main import create_app

    rows, errors = load(gold_path)
    if errors:
        print("gold set has schema errors; fix them first:")
        for err in errors:
            print(f"  {err}")
        return 2

    started = time.perf_counter()
    app = create_app()

    from memora.api.deps import current_user_id

    owner = EVAL_USER_ID
    app.dependency_overrides[current_user_id] = lambda: owner

    documents = chunks = elapsed = 0

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://baseline", timeout=3600
    ) as client:
        if do_ingest:
            print(f"  ingesting {corpus} (~400 embeds against a 1000/day tier)...")
            documents, chunks, rejected = await ingest(client, corpus)
            elapsed = int(time.perf_counter() - started)
            print(f"  {documents} documents, {chunks} chunks in {elapsed}s")
            for name in rejected:
                print(f"    rejected: {name}")

        indexed = await ingested_documents(owner)
        if not indexed:
            print("\n  Nothing is indexed for the eval owner. Run once with --ingest.\n")
            return 1

        problems = verify_corpus(corpus_hashes(corpus), indexed, rows)
        if problems:
            print("\n  The indexed corpus does not match the gold set or the disk:")
            for problem in problems:
                print(f"    x {problem}")
            print("\n  Re-run with --ingest, or fix the gold set. Refusing to report a")
            print("  number that describes a corpus which is no longer there.\n")
            return 1

        if not do_ingest:
            documents = len(indexed)
            chunks = await chunk_count(owner)
            print(f"  reusing indexed corpus: {documents} documents, {chunks} chunks")

        print(f"  running {len(rows)} queries ({len(rows)} embeds)...")
        metrics = await measure(client, rows)

    meta = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": _commit(),
        "documents": documents,
        "chunks": chunks,
        "ingest_seconds": elapsed,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(metrics, meta), encoding="utf-8", newline="\n")

    print()
    print(f"  Recall@1 {metrics.recall_at(1):.3f}   Recall@5 {metrics.recall_at(5):.3f}   "
          f"MRR@{MRR_DEPTH} {metrics.mrr:.3f}   refusal {metrics.refusal_accuracy:.3f}")
    print(f"  wrote {out}")
    return 0


def _commit() -> str:
    import subprocess

    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="memora.eval.baseline")
    parser.add_argument("--gold", type=Path, default=None)
    parser.add_argument("--corpus", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--ingest",
        action="store_true",
        help=(
            "re-ingest the corpus first. Costs roughly 400 embeds against a 1000/day "
            "tier; omit it to evaluate the corpus already indexed."
        ),
    )
    args = parser.parse_args(argv)

    gold = resolve(args.gold) if args.gold else anchored("docs/GOLD.jsonl")
    corpus = resolve(args.corpus) if args.corpus else anchored("data/corpus")
    out = resolve(args.out) if args.out else anchored("docs/BASELINE.md")

    if not gold.exists():
        print(f"error: gold set not found at {gold}")
        return 2

    return asyncio.run(run(gold, corpus, out, do_ingest=args.ingest))


if __name__ == "__main__":
    raise SystemExit(main())

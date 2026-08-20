"""Gold-set evaluation harness.

Retrieval does not exist yet, so today this validates the gold set itself: schema,
coverage across query types, and whether every ``expected_sources`` file is actually
present in the corpus.

That last check is the point. It turns "did we build the gold set?" from a question
into a command that exits non-zero until the answer is yes.

    python -m memora.eval.retrieval docs/GOLD.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from memora.paths import resolve

REQUIRED_FIELDS = ("id", "query", "type")

KNOWN_TYPES = {
    "metadata_only",
    "temporal_resolution",
    "cross_source",
    "entity_resolution",
    "semantic",
    "must_refuse",
    "multimodal",
}

MIN_ROWS = 20



@dataclass
class GoldRow:
    id: str
    query: str
    type: str
    expected_sources: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class Report:
    rows: list[GoldRow] = field(default_factory=list)
    schema_errors: list[str] = field(default_factory=list)
    missing_sources: dict[str, list[str]] = field(default_factory=dict)

    @property
    def missing_types(self) -> list[str]:
        counts = Counter(r.type for r in self.rows)
        return sorted(t for t in KNOWN_TYPES if not counts.get(t))

    @property
    def ok(self) -> bool:
        return (
            not self.schema_errors
            and not self.missing_sources
            and not self.missing_types
            and len(self.rows) >= MIN_ROWS
        )


def load(path: Path) -> tuple[list[GoldRow], list[str]]:
    rows: list[GoldRow] = []
    errors: list[str] = []
    seen_ids: set[str] = set()

    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {lineno}: invalid JSON - {exc.msg}")
            continue

        # Comment/metadata rows are ignored, not errors.
        if all(str(k).startswith("_") for k in obj):
            continue

        missing = [f for f in REQUIRED_FIELDS if f not in obj]
        if missing:
            errors.append(f"line {lineno}: missing field(s) {', '.join(missing)}")
            continue

        if obj["id"] in seen_ids:
            errors.append(f"line {lineno}: duplicate id '{obj['id']}'")
        seen_ids.add(obj["id"])

        if obj["type"] not in KNOWN_TYPES:
            errors.append(
                f"line {lineno}: unknown type '{obj['type']}' "
                f"(expected one of {', '.join(sorted(KNOWN_TYPES))})"
            )

        rows.append(
            GoldRow(
                id=obj["id"],
                query=obj["query"],
                type=obj["type"],
                expected_sources=list(obj.get("expected_sources", [])),
                raw=obj,
            )
        )

    return rows, errors


def check_corpus(rows: list[GoldRow], corpus: Path) -> dict[str, list[str]]:
    """Every expected_sources filename must exist in the corpus directory."""
    if not corpus.exists():
        return {r.id: r.expected_sources for r in rows if r.expected_sources}

    present = {p.name for p in corpus.rglob("*") if p.is_file() and not p.name.startswith(".")}
    missing: dict[str, list[str]] = {}
    for row in rows:
        gone = [s for s in row.expected_sources if s not in present]
        if gone:
            missing[row.id] = gone
    return missing


def render(report: Report, corpus: Path) -> None:
    rows = report.rows
    print()
    print("=" * 62)
    print("  MEMORA GOLD SET")
    print("=" * 62)

    if report.schema_errors:
        print(f"\n  SCHEMA ERRORS ({len(report.schema_errors)})")
        for err in report.schema_errors:
            print(f"    x {err}")

    counts = Counter(r.type for r in rows)
    print(f"\n  {len(rows)} queries by type")
    for qtype in sorted(KNOWN_TYPES):
        n = counts.get(qtype, 0)
        mark = " " if n else "!"
        print(f"    {mark} {qtype:<22} {n}")

    print(f"\n  Corpus: {corpus}")
    if not corpus.exists():
        print("    x directory does not exist")
    else:
        n_files = sum(
            1 for p in corpus.rglob('*') if p.is_file() and not p.name.startswith('.')
        )
        print(f"    {n_files} file(s)")

    if report.missing_sources:
        n = sum(len(v) for v in report.missing_sources.values())
        print(f"\n  MISSING SOURCE FILES ({n})")
        for qid, names in sorted(report.missing_sources.items()):
            for name in names:
                print(f"    x {qid}: {name}")

    print("\n" + "-" * 62)
    if report.ok:
        print("  PASS - gold set is well-formed and every source file exists.")
        print()
        print("  This does NOT mean retrieval works. It means the gold set is")
        print("  ready to measure retrieval once retrieval exists. Recall@k,")
        print("  NDCG@k and refusal accuracy replace this check after the")
        print("  vertical slice lands.")
    else:
        print("  NOT READY")
        if len(rows) < MIN_ROWS:
            print(f"    - {len(rows)} queries, target is {MIN_ROWS}+")
        if report.missing_types:
            print(f"    - no coverage for: {', '.join(report.missing_types)}")
        if report.missing_sources:
            print(f"    - {len(report.missing_sources)} row(s) point at files not in {corpus}")
            print("      Step 1 is unfinished: drop your real files in, then fix these names.")
    print("-" * 62 + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="memora.eval.retrieval")
    parser.add_argument("gold", type=Path, nargs="?", default=Path("docs/GOLD.jsonl"))
    parser.add_argument("--corpus", type=Path, default=Path("data/corpus"))
    args = parser.parse_args(argv)

    args.gold = resolve(args.gold)
    args.corpus = resolve(args.corpus)

    if not args.gold.exists():
        print(f"error: gold set not found at {args.gold}", file=sys.stderr)
        return 2

    rows, schema_errors = load(args.gold)
    report = Report(
        rows=rows,
        schema_errors=schema_errors,
        missing_sources=check_corpus(rows, args.corpus),
    )
    render(report, args.corpus)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

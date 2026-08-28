"""What would adding a file to the corpus do to the gold set?

Adding a document does not only make rows answerable — it can **invalidate controls**, and
that has already happened once. When CLIP made images ingestable, q019 stopped being a
guaranteed miss and silently became a normal row: the experiment ate the falsifier that
proved it could fail. Two replacement controls had to be written after the fact.

This answers the question before the file lands rather than after:

    uv run python -m memora.eval.impact --add data/corpus/college_id.jpg
    uv run python -m memora.eval.impact --add a.jpg --add b.jpg

Costs nothing. It reads the gold set and the filename; it does not ingest, embed, OCR or
call any model. It therefore reasons about **what the gold set says**, not about what the
retriever would do — the limits of that are printed with the report rather than implied.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

from memora.eval.retrieval import GoldRow, load
from memora.paths import anchored, resolve
from memora.services.document_type import classify

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif", ".bmp"}


@dataclass
class Impact:
    filename: str
    guessed_type: str | None
    is_image: bool
    answers: list[GoldRow] = field(default_factory=list)
    breaks_refusal: list[GoldRow] = field(default_factory=list)
    at_risk_visual: list[GoldRow] = field(default_factory=list)
    fills_type_gap: list[str] = field(default_factory=list)


def assess(path: Path, rows: list[GoldRow], covered_types: set[str]) -> Impact:
    name = path.name
    suffix = path.suffix.lower()
    is_image = suffix in IMAGE_SUFFIXES

    # Filename only. The real classifier also reads the head of the extracted text, so a
    # file whose name says nothing may still classify once OCR runs - reported as a limit
    # rather than guessed at here.
    guessed = classify(filename=name)

    impact = Impact(filename=name, guessed_type=guessed, is_image=is_image)

    for row in rows:
        if name in row.expected_sources:
            impact.answers.append(row)
            continue

        if row.type != "must_refuse":
            continue

        # A refusal row asking for a type this file would satisfy stops being a refusal.
        if guessed and guessed in (row.raw.get("expected_document_type"), _implied_type(row)):
            impact.breaks_refusal.append(row)
        elif is_image and _is_visual_absence(row):
            # CLIP returns a nearest neighbour for every query, so any new image is a new
            # candidate for a visual refusal row. Not a certainty - a warning.
            impact.at_risk_visual.append(row)

    if guessed and guessed not in covered_types:
        impact.fills_type_gap.append(guessed)

    return impact


def _implied_type(row: GoldRow) -> str | None:
    """The document type a must_refuse row is asking for, read from its own query."""
    from memora.services.document_type import VOCABULARY

    query = row.query.lower()
    for label, synonyms in VOCABULARY.items():
        if label.replace("_", " ") in query or any(word in query for word in synonyms):
            return label
    return None


def _is_visual_absence(row: GoldRow) -> bool:
    """A refusal row about a picture rather than a document type."""
    note = (row.raw.get("notes") or "").lower()
    query = row.query.lower()
    return "visual" in note or any(
        word in query for word in ("photo", "picture", "image", "group photo")
    )


def render(impacts: list[Impact], rows: list[GoldRow]) -> list[str]:
    out: list[str] = []
    answerable = {r.id for i in impacts for r in i.answers}
    broken = {r.id for i in impacts for r in i.breaks_refusal}
    at_risk = {r.id for i in impacts for r in i.at_risk_visual}

    for impact in impacts:
        out.append(f"\n  {impact.filename}")
        out.append(
            f"    would classify as : {impact.guessed_type or 'no type from the filename'}"
        )

        if impact.answers:
            out.append("    ANSWERS these rows:")
            for row in impact.answers:
                out.append(f"      + {row.id}  [{row.type}]  {row.query[:52]}")
        else:
            out.append("    answers no gold row - no row expects this filename")

        if impact.breaks_refusal:
            out.append("    INVALIDATES these refusal controls:")
            for row in impact.breaks_refusal:
                out.append(
                    f"      ! {row.id}  {row.query[:44]}  (asks for a type this file has)"
                )

        if impact.at_risk_visual:
            out.append("    PUTS AT RISK these visual absence controls:")
            for row in impact.at_risk_visual:
                out.append(f"      ? {row.id}  {row.query[:44]}")

        if impact.fills_type_gap:
            out.append(f"    fills a type gap: {', '.join(impact.fills_type_gap)}")

    out.append("")
    out.append("  " + "-" * 60)
    refusal_rows = [r for r in rows if r.type == "must_refuse"]
    surviving = [r for r in refusal_rows if r.id not in broken and r.id not in at_risk]
    out.append(f"  gold rows made answerable : {len(answerable)}")
    out.append(f"  refusal controls broken   : {len(broken)}")
    out.append(f"  refusal controls at risk  : {len(at_risk)}")
    out.append(
        f"  refusal controls surviving: {len(surviving)} of {len(refusal_rows)}"
        f"  {sorted(r.id for r in surviving)}"
    )

    if not surviving:
        out.append("")
        out.append("  *** NO REFUSAL CONTROL WOULD SURVIVE. ***")
        out.append("  Write a replacement BEFORE adding these files. An experiment with no")
        out.append("  falsifier cannot fail, and q019 was lost exactly this way.")
    elif broken or at_risk:
        out.append("")
        out.append("  Write replacement controls for the broken ones in the same change")
        out.append("  that adds these files, not afterwards.")

    out.append("")
    out.append("  What this CANNOT tell you:")
    out.append("    - whether the file will actually rank first; that needs a real run")
    out.append("    - what OCR will read, which can change the classified type")
    out.append("    - whether an added image will out-rank an unrelated query visually")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--add", action="append", required=True, metavar="PATH",
        help="a file you are considering adding; repeatable",
    )
    parser.add_argument("--gold", default=None)
    args = parser.parse_args(argv)

    gold_path = resolve(args.gold) if args.gold else anchored("docs/GOLD.jsonl")
    rows, errors = load(gold_path)
    if errors:
        print("gold set has schema errors; fix them first:")
        for err in errors:
            print(f"  {err}")
        return 2

    covered = {r.raw.get("expected_document_type") for r in rows}
    covered.discard(None)

    refusals = len([r for r in rows if r.type == "must_refuse"])
    print(f"  gold set: {len(rows)} rows, {refusals} refusal")
    impacts = [assess(Path(p), rows, covered) for p in args.add]
    for line in render(impacts, rows):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""OCR benchmark - PaddleOCR vs Tesseract vs Gemini Flash vision.

Settles a phase 4 architecture decision with a number instead of an opinion, and the
table it prints goes into chapter 6.

Built before the images exist, deliberately. The corpus check runs with only the
default dependencies installed, so this tells you what is missing today and runs in
minutes once you have collected the images.

    data/ocr-bench/
      images/<category>/<name>.png     the image
      refs/<category>/<name>.txt       what it actually says

Categories are the ones that behave differently under OCR - a handwriting result and
a printed-page result averaged together hide the only finding that matters.

    uv sync --group bench
    uv run python -m memora.bench.ocr                       # tesseract + paddleocr
    uv run python -m memora.bench.ocr --engines gemini-flash  # costs money, opt in
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from memora.bench.engines import ENGINES, OcrEngine
from memora.paths import resolve

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

REQUIRED_CATEGORIES = {
    "printed",
    "book_photo",
    "screenshot",
    "whiteboard",
    "handwritten",
}

MIN_IMAGES = 20

nl = chr(10)

# Gemini is metered. It is never included unless the caller names it.
DEFAULT_ENGINES = ("tesseract", "paddleocr")


@dataclass(frozen=True)
class Sample:
    image: Path
    category: str
    stem: str
    reference: Path | None


@dataclass
class Measurement:
    engine: str
    category: str
    stem: str
    cer: float | None = None
    wer: float | None = None
    seconds: float = 0.0
    error: str | None = None


@dataclass
class Corpus:
    samples: list[Sample] = field(default_factory=list)
    missing_refs: list[str] = field(default_factory=list)

    @property
    def categories(self) -> set[str]:
        return {s.category for s in self.samples}

    @property
    def missing_categories(self) -> list[str]:
        return sorted(REQUIRED_CATEGORIES - self.categories)

    @property
    def ok(self) -> bool:
        return (
            len(self.samples) >= MIN_IMAGES
            and not self.missing_refs
            and not self.missing_categories
        )


def discover(images_root: Path, refs_root: Path) -> Corpus:
    corpus = Corpus()
    if not images_root.exists():
        return corpus

    for path in sorted(images_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        rel = path.relative_to(images_root)
        category = rel.parts[0] if len(rel.parts) > 1 else "uncategorized"
        ref = refs_root / rel.with_suffix(".txt")
        if ref.exists():
            corpus.samples.append(Sample(path, category, rel.stem, ref))
        else:
            corpus.samples.append(Sample(path, category, rel.stem, None))
            corpus.missing_refs.append(str(rel.with_suffix(".txt")))

    return corpus


def normalize(text: str, *, lowercase: bool) -> str:
    """Normalization changes CER materially, so it is explicit and reported."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower() if lowercase else text


def score(reference: str, hypothesis: str) -> tuple[float, float]:
    if not reference:
        return (0.0, 0.0) if not hypothesis else (1.0, 1.0)

    import jiwer
    return float(jiwer.cer(reference, hypothesis)), float(jiwer.wer(reference, hypothesis))


def measure(engine: OcrEngine, samples: list[Sample], *, lowercase: bool) -> list[Measurement]:
    results: list[Measurement] = []
    for sample in samples:
        if sample.reference is None:
            continue
        row = Measurement(engine=engine.name, category=sample.category, stem=sample.stem)
        started = time.perf_counter()
        try:
            hypothesis = engine.read(sample.image)
            row.seconds = time.perf_counter() - started
            reference = normalize(sample.reference.read_text(encoding="utf-8"), lowercase=lowercase)
            row.cer, row.wer = score(reference, normalize(hypothesis, lowercase=lowercase))
        except Exception as exc:  # noqa: BLE001 - one bad image must not end the run
            row.seconds = time.perf_counter() - started
            row.error = f"{type(exc).__name__}: {exc}"
        results.append(row)
    return results


def probe(engine: OcrEngine, sample: Sample) -> str | None:
    """One read before the full loop.

    An engine can import cleanly and still be unable to run - paddleocr 3.7 installs
    fine on Windows and then dies in a oneDNN kernel. Without this, that shows up as
    twenty identical per-image errors and an otherwise successful run.
    """
    try:
        engine.read(sample.image)
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"
    return None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _cell(value: float | None, spec: str = "6.3f") -> str:
    return format(value, spec) if value is not None else "     -"


def render_table(rows: list[Measurement], engines: list[str], categories: list[str]) -> list[str]:
    width = max([len(c) for c in categories] + [len("category"), len("OVERALL")])
    header = "  " + "category".ljust(width) + "".join(f"  {e:>14}" for e in engines)
    lines = [header, "  " + "-" * (len(header) - 2)]

    for category in [*categories, "OVERALL"]:
        scoped = rows if category == "OVERALL" else [r for r in rows if r.category == category]
        cells = []
        for engine in engines:
            values = [r.cer for r in scoped if r.engine == engine and r.cer is not None]
            cells.append(f"  {_cell(_mean(values)):>14}")
        lines.append("  " + category.ljust(width) + "".join(cells))

    lines.append("")
    lines.append("  " + "seconds/image".ljust(width) + "".join(f"  {e:>14}" for e in engines))
    speed = []
    for engine in engines:
        values = [r.seconds for r in rows if r.engine == engine and r.error is None]
        speed.append(f"  {_cell(_mean(values)):>14}")
    lines.append("  " + "".ljust(width) + "".join(speed))
    return lines


def render_corpus_status(corpus: Corpus, images_root: Path) -> list[str]:
    lines = [f"  Images: {images_root}", f"    {len(corpus.samples)} image(s)"]
    for category in sorted(REQUIRED_CATEGORIES | corpus.categories):
        n = sum(1 for s in corpus.samples if s.category == category)
        lines.append(f"    {' ' if n else '!'} {category:<14} {n}")

    if corpus.missing_refs:
        lines.append("")
        lines.append(f"  MISSING REFERENCE TRANSCRIPTS ({len(corpus.missing_refs)})")
        lines.extend(f"    x {name}" for name in corpus.missing_refs[:12])
        if len(corpus.missing_refs) > 12:
            lines.append(f"    ... and {len(corpus.missing_refs) - 12} more")
    return lines


def write_report(path: Path, rows: list[Measurement], engines: list[str], meta: dict) -> None:
    categories = sorted({r.category for r in rows})
    body = [
        "# OCR benchmark",
        "",
        f"Generated {meta['generated_at']} - {meta['images']} images, "
        f"normalization: {meta['normalization']}.",
        "",
        "Mean CER by category (lower is better).",
        "",
        "| category | " + " | ".join(engines) + " |",
        "|---|" + "---|" * len(engines),
    ]
    for category in [*categories, "**overall**"]:
        scoped = rows if category.startswith("**") else [r for r in rows if r.category == category]
        cells = []
        for engine in engines:
            values = [r.cer for r in scoped if r.engine == engine and r.cer is not None]
            mean = _mean(values)
            cells.append(f"{mean:.3f}" if mean is not None else "-")
        body.append(f"| {category} | " + " | ".join(cells) + " |")

    errors = [r for r in rows if r.error]
    if errors:
        body += ["", f"{len(errors)} image(s) errored:", ""]
        body += [f"- `{r.engine}` on `{r.category}/{r.stem}` - {r.error}" for r in errors[:10]]

    path.write_text("\n".join(body) + "\n", encoding="utf-8", newline="\n")
    path.with_suffix(".json").write_text(
        json.dumps(
            {"meta": meta, "measurements": [vars(r) for r in rows]}, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="memora.bench.ocr")
    parser.add_argument("--images", type=Path, default=Path("data/ocr-bench/images"))
    parser.add_argument("--refs", type=Path, default=Path("data/ocr-bench/refs"))
    parser.add_argument("--out", type=Path, default=Path("docs/ocr-benchmark.md"))
    parser.add_argument(
        "--engines",
        nargs="+",
        default=list(DEFAULT_ENGINES),
        choices=sorted(ENGINES),
        help="gemini-flash is metered and must be named explicitly",
    )
    parser.add_argument("--limit", type=int, default=None, help="run the first N images only")
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="compare without lowercasing (raises CER for every engine)",
    )
    args = parser.parse_args(argv)

    images_root, refs_root = resolve(args.images), resolve(args.refs)
    corpus = discover(images_root, refs_root)

    print()
    print("=" * 62)
    print("  MEMORA OCR BENCHMARK")
    print("=" * 62)
    print()
    for line in render_corpus_status(corpus, images_root):
        print(line)

    if not corpus.ok:
        print()
        print("-" * 62)
        print("  NOT READY - no engine was run")
        if len(corpus.samples) < MIN_IMAGES:
            print(f"    - {len(corpus.samples)} images, target is {MIN_IMAGES}+")
        if corpus.missing_categories:
            print(f"    - no coverage for: {', '.join(corpus.missing_categories)}")
        if corpus.missing_refs:
            print(f"    - {len(corpus.missing_refs)} image(s) have no reference transcript")
            print(f"      Each image needs its true text at {refs_root}/<category>/<name>.txt")
        print("-" * 62)
        print()
        return 1

    selected: list[OcrEngine] = []
    print()
    print("  Engines")
    for name in args.engines:
        engine = ENGINES[name]()
        state = engine.availability()
        print(f"    {'ok ' if state.ok else 'x  '} {engine.name:<14} {state.detail}")
        if state.ok:
            selected.append(engine)

    if not selected:
        print("\n  No engine available. Install with: uv sync --group bench\n")
        return 1

    samples = corpus.samples[: args.limit] if args.limit else corpus.samples
    lowercase = not args.case_sensitive

    working: list[OcrEngine] = []
    for engine in selected:
        failure = probe(engine, samples[0])
        if failure is None:
            working.append(engine)
        else:
            print(f"    x  {engine.name:<14} cannot run - {failure[:80]}")

    if not working:
        print(nl + "  No engine could run. Nothing was measured." + nl)
        return 1

    rows: list[Measurement] = []
    for engine in working:
        print(nl + f"  running {engine.name} over {len(samples)} image(s)...")
        rows.extend(measure(engine, samples, lowercase=lowercase))

    if not any(r.cer is not None for r in rows):
        print(nl + "  Every image errored. No CER produced, nothing to report." + nl)
        return 1

    names = [e.name for e in working]
    print()
    print("  Mean CER by category (lower is better)")
    print()
    for line in render_table(rows, names, sorted({r.category for r in rows})):
        print(line)

    meta = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "images": len(samples),
        "engines": names,
        "normalization": "NFKC, collapsed whitespace"
        + (", lowercased" if lowercase else ", case sensitive"),
    }
    out = resolve(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_report(out, rows, names, meta)
    print(f"\n  wrote {out} and {out.with_suffix('.json')}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

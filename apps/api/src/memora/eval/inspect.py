"""Corpus inspector.

Lists what is actually in data/corpus/ and emits a skeleton gold set with one row
per file, so writing the queries becomes a reading task rather than a remembering
task - the preview sits next to the blank query field.

It does NOT write queries. A gold query depends on how you would have asked for a
file from memory, which is not recoverable from the file's contents. Machine fills
the filename and the preview; you fill the sentence.

Read-only on the corpus. Nothing is moved, renamed, or modified.

    uv run python -m memora.eval.inspect
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from memora.paths import resolve

PREVIEW_CHARS = 200

PDF_SUFFIXES = {".pdf"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic"}
AUDIO_SUFFIXES = {".m4a", ".mp3", ".wav", ".ogg", ".flac", ".aac", ".opus"}
TEXT_SUFFIXES = {".txt", ".md", ".eml", ".csv", ".json", ".ics", ".html", ".vtt", ".srt"}


@dataclass
class FileInfo:
    name: str
    kind: str
    size_bytes: int
    detail: str = ""
    preview: str = ""
    error: str | None = None


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n / 1:.0f}{unit}"
        n /= 1024
    return f"{n:.0f}GB"


def classify(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in PDF_SUFFIXES:
        return "pdf"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in AUDIO_SUFFIXES:
        return "audio"
    if suffix in TEXT_SUFFIXES:
        return "text"
    return "unknown"


def _clean(text: str) -> str:
    return " ".join(text.split())[:PREVIEW_CHARS]


# Windows consoles are cp1252. Real documents are full of smart punctuation, and
# printing it raw turns an en-dash into a replacement character mid-preview. The
# draft file is written UTF-8 and keeps the original; only the display is folded.
_FOLD = {
    "—": "-", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...", " ": " ",
    "•": "*", "→": "->",
}


def ascii_safe(text: str) -> str:
    for src, dst in _FOLD.items():
        text = text.replace(src, dst)
    return text.encode("ascii", "replace").decode("ascii")


def read_pdf(path: Path) -> tuple[str, str]:
    import pymupdf

    with pymupdf.open(path) as doc:
        pages = len(doc)
        title = (doc.metadata or {}).get("title") or ""
        text = ""
        for page in doc:
            text += page.get_text()
            if len(text) > PREVIEW_CHARS * 3:
                break
    detail = f"{pages}pp" + (f' title="{title[:40]}"' if title else "")
    body = _clean(text)
    return detail, body or "(no extractable text - scanned? needs OCR)"


def read_image(path: Path) -> tuple[str, str]:
    from PIL import Image

    with Image.open(path) as img:
        width, height = img.size
        fmt = img.format or path.suffix.lstrip(".").upper()
        taken = ""
        getexif = getattr(img, "getexif", None)
        if getexif is not None:
            exif = getexif()
            # 36867 DateTimeOriginal, 306 DateTime
            taken = str(exif.get(36867) or exif.get(306) or "")
    detail = f"{width}x{height} {fmt}" + (f" taken={taken}" if taken else " taken=unknown")
    return detail, "(image - text content unknown until OCR runs in phase 4)"


def read_audio(path: Path) -> tuple[str, str]:
    from mutagen import File as MutagenFile

    audio = MutagenFile(path)
    if audio is None or audio.info is None:
        return "unreadable audio", "(no duration available)"
    seconds = int(getattr(audio.info, "length", 0))
    detail = f"{seconds // 60}m{seconds % 60:02d}s"
    return detail, "(audio - transcript unknown until Whisper runs in phase 4)"


def read_text(path: Path) -> tuple[str, str]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = [ln for ln in raw.splitlines() if ln.strip()][:4]
    return f"{len(raw.splitlines())} lines", _clean(" / ".join(lines))


READERS = {"pdf": read_pdf, "image": read_image, "audio": read_audio, "text": read_text}


def inspect_file(path: Path) -> FileInfo:
    info = FileInfo(name=path.name, kind=classify(path), size_bytes=path.stat().st_size)
    reader = READERS.get(info.kind)
    if reader is None:
        info.preview = "(unrecognised type - no reader)"
        return info
    try:
        info.detail, info.preview = reader(path)
    except Exception as exc:  # noqa: BLE001 - one bad file must not end the listing
        info.error = f"{type(exc).__name__}: {exc}"
        info.preview = "(unreadable)"
    return info


def inspect_corpus(corpus: Path) -> list[FileInfo]:
    if not corpus.exists():
        return []
    files = sorted(
        (p for p in corpus.rglob("*") if p.is_file() and not p.name.startswith(".")),
        key=lambda p: p.name.lower(),
    )
    return [inspect_file(p) for p in files]


def render(rows: list[FileInfo], corpus: Path) -> None:
    print()
    print("=" * 78)
    print("  CORPUS")
    print("=" * 78)
    print(f"\n  {corpus}")
    if not rows:
        print("\n  empty\n")
        return

    width = min(max(len(r.name) for r in rows), 44)
    for i, row in enumerate(rows, 1):
        raw = ascii_safe(row.name)
        name = raw if len(raw) <= width else raw[: width - 3] + "..."
        print(f"\n  {i:>2}. {name:<{width}}  {row.kind:<7} {human_size(row.size_bytes):>7}")
        if row.detail:
            print(f"      {ascii_safe(row.detail)}")
        if row.error:
            print(f"      ERROR {ascii_safe(row.error)}")
        print(f"      {ascii_safe(row.preview)}")

    kinds: dict[str, int] = {}
    for row in rows:
        kinds[row.kind] = kinds.get(row.kind, 0) + 1
    print(f"\n  {len(rows)} file(s): " + ", ".join(f"{v} {k}" for k, v in sorted(kinds.items())))


def write_draft(rows: list[FileInfo], out: Path) -> None:
    lines = [
        json.dumps(
            {
                "_comment": (
                    "DRAFT. For each row: read _preview, then write the one sentence you "
                    "would have used to ask for that file from memory. Fill query and type, "
                    "delete _preview, rename to GOLD.jsonl. Types: metadata_only, "
                    "temporal_resolution, cross_source, entity_resolution, semantic, "
                    "must_refuse, multimodal."
                )
            }
        )
    ]
    for i, row in enumerate(rows, 1):
        lines.append(
            json.dumps(
                {
                    "id": f"q{i:03d}",
                    "query": "",
                    "type": None,
                    "expected_sources": [row.name],
                    "_preview": row.preview,
                }
            )
        )
    # must_refuse cites nothing by definition, so it can never be generated per-file -
    # and the gate fails without one. Skeleton only; the query is still yours.
    lines.append(
        json.dumps(
            {
                "id": f"q{len(rows) + 1:03d}",
                "query": "",
                "type": "must_refuse",
                "expected_sources": [],
                "_preview": "(no file - ask for something you never stored)",
            }
        )
    )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="memora.eval.inspect")
    parser.add_argument("--corpus", type=Path, default=Path("data/corpus"))
    parser.add_argument("--out", type=Path, default=Path("docs/GOLD.jsonl.draft"))
    args = parser.parse_args(argv)

    corpus = resolve(args.corpus)
    rows = inspect_corpus(corpus)
    render(rows, corpus)

    if not rows:
        return 1

    out = resolve(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_draft(rows, out)
    print(f"\n  wrote {out}")
    print("  Fill in query and type, delete _preview, rename to GOLD.jsonl\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""PDF text extraction with PyMuPDF."""

from __future__ import annotations

from memora.services.chunking import Block

PDF_MAGIC = b"%PDF"
# Font size relative to the page's body text, above which a line reads as a heading.
HEADING_RATIO = 1.15


def is_pdf(data: bytes) -> bool:
    """Sniff the magic bytes. A filename extension is a claim, not evidence."""
    return data[:4] == PDF_MAGIC


def extract_blocks(data: bytes) -> tuple[str, list[Block]]:
    """Return (document title, structural blocks) from PDF bytes."""
    import pymupdf

    with pymupdf.open(stream=data, filetype="pdf") as doc:
        title = (doc.metadata or {}).get("title") or ""
        sizes: list[float] = []
        pages: list[list[tuple[str, float]]] = []

        for page in doc:
            lines: list[tuple[str, float]] = []
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    text = "".join(span["text"] for span in line["spans"]).strip()
                    if not text:
                        continue
                    size = max((span["size"] for span in line["spans"]), default=0.0)
                    lines.append((text, size))
                    sizes.append(size)
            pages.append(lines)

    body_size = _median(sizes) if sizes else 0.0
    blocks: list[Block] = []
    for lines in pages:
        for text, size in lines:
            is_heading = size > body_size * HEADING_RATIO and len(text) < 120
            blocks.append(Block(text=text, heading=text if is_heading else None))

    if not title:
        title = next((b.heading for b in blocks if b.heading), "") or "Untitled"
    return title.strip()[:512], blocks


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2

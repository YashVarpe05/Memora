"""Text extraction. PDFs via PyMuPDF, images via the OCR service."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from memora.services.chunking import Block

if TYPE_CHECKING:
    from memora.services.ocr import OcrClient

PDF_MAGIC = b"%PDF"

# Magic bytes, not extensions. A filename is a claim; these are evidence.
PNG_MAGIC = bytes([0x89]) + b"PNG\r\n" + bytes([0x1A]) + b"\n"
JPEG_MAGIC = bytes([0xFF, 0xD8, 0xFF])

IMAGE_MAGIC: tuple[tuple[bytes, str], ...] = (
    (PNG_MAGIC, "image/png"),
    (JPEG_MAGIC, "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
)

# Font size relative to the page's body text, above which a line reads as a heading.
HEADING_RATIO = 1.15


def is_pdf(data: bytes) -> bool:
    """Sniff the magic bytes. A filename extension is a claim, not evidence."""
    return data[:4] == PDF_MAGIC


def image_mime(data: bytes) -> str | None:
    """Return the image mime type, or None when the bytes are not a known image."""
    for magic, mime in IMAGE_MAGIC:
        if data.startswith(magic):
            return mime
    # WebP is RIFF....WEBP
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def extract_blocks(data: bytes) -> tuple[str, list[Block]]:
    """Return (document title, structural blocks) from PDF bytes."""
    # `fitz` is the legacy alias and is deprecated; `pymupdf` is the supported name.
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
    for page_number, lines in enumerate(pages, start=1):
        for text, size in lines:
            is_heading = size > body_size * HEADING_RATIO and len(text) < 120
            blocks.append(
                Block(
                    text=text,
                    heading=text if is_heading else None,
                    page=page_number,
                )
            )

    if not title:
        title = next((b.heading for b in blocks if b.heading), "") or "Untitled"
    return title.strip()[:512], blocks


async def extract_image_blocks(
    data: bytes, ocr: OcrClient, filename: str = "upload"
) -> tuple[str, list[Block]]:
    """OCR an image into blocks, one per non-empty line.

    An image has no font metrics to infer structure from, so the title falls back to the
    filename. That is often meaningful in practice - "WhatsApp Image 2026-07-03" carries
    a date, and a camera filename carries nothing, which is itself information.
    """
    text = await ocr.read(data, filename)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = Path(filename).stem[:512] or "Image"
    return title, [Block(text=line) for line in lines]


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


async def extract_pdf_via_ocr(
    data: bytes, ocr: OcrClient, filename: str = "upload.pdf", max_pages: int = 20
) -> tuple[str, list[Block]]:
    """OCR a PDF that has no text layer, by rendering each page and reading the pixels.

    This is the mail.pdf case PRODUCT.md points at: four pages, zero extractable text,
    because it is a printed email saved as images. Without this path such a document is
    unfindable, which is the whole failure the product exists to fix.
    """
    import pymupdf

    with pymupdf.open(stream=data, filetype="pdf") as doc:
        title = (doc.metadata or {}).get("title") or Path(filename).stem
        # 200 dpi: enough for body text, without making the OCR call enormous.
        pages = [
            page.get_pixmap(dpi=200).tobytes("png")
            for page in list(doc)[:max_pages]
        ]

    blocks: list[Block] = []
    for number, png in enumerate(pages, start=1):
        text = await ocr.read(png, f"{filename}#page{number}")
        blocks.extend(
            Block(text=line.strip(), page=number)
            for line in text.splitlines()
            if line.strip()
        )

    return str(title).strip()[:512] or "Untitled", blocks

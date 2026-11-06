"""Text extraction. PDFs via PyMuPDF, images via the OCR service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from memora.services.chunking import Block
from memora.services.parsers.calendar import is_calendar, parse_calendar
from memora.services.parsers.chat import group_conversations, looks_like_chat, parse_chat
from memora.services.parsers.email import is_email, parse_email

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
        pages = [page.get_pixmap(dpi=200).tobytes("png") for page in list(doc)[:max_pages]]

    blocks: list[Block] = []
    for number, png in enumerate(pages, start=1):
        text = await ocr.read(png, f"{filename}#page{number}")
        blocks.extend(
            Block(text=line.strip(), page=number) for line in text.splitlines() if line.strip()
        )

    return str(title).strip()[:512] or "Untitled", blocks


@dataclass(frozen=True)
class Extracted:
    """What a format parser hands back to the upload route."""

    title: str
    blocks: list[Block]
    source_type: str
    # One chunk per block for calendar and chat, where the structure is the unit of
    # meaning; the token window for prose.
    per_block: bool = False
    sender: str | None = None
    occurred_at: datetime | None = None


def text_kind(data: bytes) -> str | None:
    """Recognise a text format from its content. Returns calendar | email | chat | None."""
    if is_calendar(data):
        return "calendar"
    if is_email(data):
        return "email"
    try:
        sample = data[:4096].decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    return "chat" if looks_like_chat(sample) else None


def extract_calendar(data: bytes, filename: str) -> Extracted:
    name, events = parse_calendar(data)
    blocks = [
        Block(
            text=event.render(),
            heading=event.summary[:120],
            occurred_at=event.starts_at,
            meta=event.meta,
        )
        for event in events
    ]
    starts = [e.starts_at for e in events if e.starts_at]
    return Extracted(
        title=name or Path(filename).stem,
        blocks=blocks,
        source_type="calendar",
        per_block=True,
        occurred_at=min(starts) if starts else None,
    )


def extract_email(data: bytes, filename: str) -> Extracted:
    parsed = parse_email(data)
    body = parsed.body or parsed.subject
    return Extracted(
        title=parsed.subject,
        blocks=[
            Block(text=paragraph.strip(), heading=parsed.subject[:120], occurred_at=parsed.sent_at)
            for paragraph in body.split("\n\n")
            if paragraph.strip()
        ],
        source_type="email",
        sender=parsed.sender or None,
        occurred_at=parsed.sent_at,
    )


def extract_chat(data: bytes, filename: str) -> Extracted:
    text = data.decode("utf-8", errors="replace")
    conversations = group_conversations(parse_chat(text))
    blocks = [
        Block(
            text=conversation.render(),
            heading=", ".join(conversation.participants[:3])[:120],
            occurred_at=conversation.starts_at,
            meta={
                "participants": conversation.participants,
                "messages": len(conversation.messages),
                "ends_at": conversation.ends_at.isoformat() if conversation.ends_at else None,
            },
        )
        for conversation in conversations
    ]
    starts = [c.starts_at for c in conversations if c.starts_at]
    return Extracted(
        title=Path(filename).stem[:512] or "Chat",
        blocks=blocks,
        source_type="chat",
        per_block=True,
        occurred_at=min(starts) if starts else None,
    )


class DocumentError(ValueError):
    """An actionable, permanent extraction failure."""


async def extract_pdf(data: bytes, ocr: OcrClient, filename: str) -> tuple[str, list[Block]]:
    """Read every page; OCR pages containing scans even in mixed-content PDFs."""
    import asyncio

    import pymupdf

    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if doc.needs_pass:
                raise DocumentError("Password-protected PDF. Save an unlocked copy to index it.")
            if len(doc) > 500:
                raise DocumentError("PDF exceeds 500 pages. Split it into smaller documents.")
            title = (doc.metadata or {}).get("title") or Path(filename).stem
            blocks: list[Block] = []
            for number, page in enumerate(doc, 1):
                text = page.get_text().strip()
                if not text or page.get_images():
                    png = await asyncio.to_thread(
                        lambda p=page: p.get_pixmap(
                            matrix=pymupdf.Matrix(
                                min(200 / 72, 2400 / max(p.rect.width, p.rect.height)),
                                min(200 / 72, 2400 / max(p.rect.width, p.rect.height)),
                            )
                        ).tobytes("png")
                    )
                    scanned = await ocr.read(png, f"{filename}#page{number}")
                    # OCR the rendered page, which includes the text layer. Preserve native
                    # text as well when OCR misses it, without duplicating identical lines.
                    text = "\n".join(dict.fromkeys((text + "\n" + scanned).splitlines()))
                blocks.extend(
                    Block(text=line.strip(), page=number)
                    for line in text.splitlines()
                    if line.strip()
                )
            return str(title)[:512], blocks
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise DocumentError("This PDF is damaged or cannot be read.") from exc


def extract_office_or_text(data: bytes, filename: str) -> Extracted:
    import io
    import subprocess
    import tempfile
    import zipfile
    from xml.etree import ElementTree

    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                info = archive.getinfo("word/document.xml")
                if info.file_size > 20 * 1024 * 1024:
                    raise DocumentError("Word document expands beyond the extraction limit.")
                xml = archive.read(info)
                if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                    raise DocumentError("Unsupported Word XML declarations.")
                root = ElementTree.fromstring(xml)
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                text = "\n".join("".join(p.itertext()) for p in root.findall(".//w:p", ns))
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
            raise DocumentError(
                "Unreadable or encrypted Word document. Save an unlocked copy."
            ) from exc
    elif suffix == ".doc":
        try:
            with tempfile.NamedTemporaryFile(suffix=".doc") as source:
                source.write(data)
                source.flush()
                result = subprocess.run(["antiword", source.name], capture_output=True, timeout=30)
            if result.returncode:
                raise DocumentError("Unreadable or encrypted Word document. Save as DOCX or PDF.")
            text = result.stdout.decode("utf-8", errors="replace")
        except FileNotFoundError as exc:
            raise DocumentError(
                "Legacy Word reader unavailable. Save this file as DOCX or PDF."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise DocumentError(
                "Word extraction timed out. Save this file as DOCX or PDF."
            ) from exc
    elif suffix in (".txt", ".md"):
        try:
            text = data.decode("utf-16" if data[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig")
        except UnicodeError as exc:
            raise DocumentError("Text encoding is unsupported. Save this file as UTF-8.") from exc
        if "\x00" in text:
            raise DocumentError("This file contains binary data, not readable text.")
    else:
        raise DocumentError("Unsupported file. Choose PDF, image, TXT, Markdown, DOC or DOCX.")
    return Extracted(
        title=Path(filename).stem[:512],
        blocks=[Block(text=line.strip()) for line in text.splitlines() if line.strip()],
        source_type="document" if suffix in (".doc", ".docx") else "note",
    )

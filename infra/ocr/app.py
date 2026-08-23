"""OCR service.

Runs inside the container so the engine works and so the ingestion path is exercised in
the environment it will actually run in. Holds no credentials and reaches no external
network.

    POST /ocr   image bytes -> {engine, text, ms}
    GET  /health            -> proves the engine can complete an inference, not just import
"""

from __future__ import annotations

import io
import os
import time
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

DEFAULT_ENGINE = os.environ.get("OCR_ENGINE", "tesseract")

app = FastAPI(title="Memora OCR", version="0.1.0")

_paddle = None


class OcrResponse(BaseModel):
    engine: str
    text: str
    ms: int


class HealthResponse(BaseModel):
    status: str
    engine: str
    # Engines that completed an inference, not engines that imported.
    available: list[str]
    installed: list[str]
    detail: str


def _installed() -> list[str]:
    """Import check only. Cheap, and says nothing about whether the engine runs."""
    import importlib.util

    engines = []
    if importlib.util.find_spec("pytesseract"):
        engines.append("tesseract")
    if importlib.util.find_spec("paddleocr") and importlib.util.find_spec("paddle"):
        engines.append("paddleocr")
    return engines


_working_cache: dict[str, bool] = {}


def _works(engine: str) -> bool:
    """Whether the engine can complete an inference, cached after the first attempt.

    paddleocr imports cleanly and then dies in a oneDNN kernel - on Windows AND in this
    container. Reporting it as available because the import succeeded is the exact
    mistake this service was built to avoid, and it was still being made one level up.
    """
    if engine not in _working_cache:
        try:
            READERS[engine](_probe_image())
            _working_cache[engine] = True
        except Exception:  # noqa: BLE001
            _working_cache[engine] = False
    return _working_cache[engine]


def _available() -> list[str]:
    """Engines that actually run. This is what dispatch and health both use."""
    return [engine for engine in _installed() if _works(engine)]


# Tesseract wants text around 300 DPI. A camera original is far past that: a
# 6000x3376 photo of an ID card is slower AND less accurate than the same image
# downscaled, because the glyph strokes end up wider than the model expects.
MAX_EDGE = 3000


def _prepare(data: bytes):
    """Normalise anything a phone or camera produces into something tesseract accepts."""
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(data))
    # A phone photo carries its rotation in EXIF rather than in the pixels. Without
    # this, a card held landscape is fed to OCR sideways and reads as noise.
    img = ImageOps.exif_transpose(img)
    # pytesseract raises "Unsupported image format/type" for modes it cannot handle -
    # CMYK, palette, RGBA. Converting is cheaper than enumerating them.
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if max(img.size) > MAX_EDGE:
        img.thumbnail((MAX_EDGE, MAX_EDGE))
    return img


def _read_tesseract(data: bytes) -> str:
    import pytesseract

    img = _prepare(data)
    try:
        return pytesseract.image_to_string(img)
    finally:
        img.close()


def _read_paddle(data: bytes) -> str:
    global _paddle
    import tempfile

    if _paddle is None:
        from paddleocr import PaddleOCR

        _paddle = PaddleOCR(
            lang="en",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        handle.write(data)
        path = handle.name

    texts: list[str] = []
    for page in _paddle.predict(path) or []:
        got = page.get("rec_texts") if hasattr(page, "get") else None
        if got:
            texts.extend(got)
    return "\n".join(texts)


READERS = {"tesseract": _read_tesseract, "paddleocr": _read_paddle}


def _probe_image() -> bytes:
    """A tiny generated image with known text, for the healthcheck."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (240, 60), "white")
    ImageDraw.Draw(img).text((10, 20), "memora ocr", fill="black")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Completes a real inference.

    An engine that imports cleanly and then dies at inference is the exact failure
    already seen with paddle on Windows. Checking the import would report healthy and
    then fail on every upload.
    """
    installed = _installed()
    working = _available()
    broken = [e for e in installed if e not in working]

    detail = "inference ok"
    if broken:
        detail = f"installed but cannot run: {', '.join(broken)}"

    if DEFAULT_ENGINE not in working:
        return HealthResponse(
            status="unhealthy",
            engine=DEFAULT_ENGINE,
            available=working,
            installed=installed,
            detail=f"{DEFAULT_ENGINE} cannot complete an inference",
        )
    return HealthResponse(
        status="ok",
        engine=DEFAULT_ENGINE,
        available=working,
        installed=installed,
        detail=detail,
    )


@app.post("/ocr", response_model=OcrResponse)
async def ocr(
    file: Annotated[UploadFile, File(...)],
    engine: Annotated[str | None, Query()] = None,
) -> OcrResponse:
    chosen = engine or DEFAULT_ENGINE
    if chosen not in READERS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"unknown engine '{chosen}'"
        )
    if chosen not in _available():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"engine '{chosen}' is not installed"
        )

    data = await file.read()
    started = time.perf_counter()
    try:
        text = READERS[chosen](data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{type(exc).__name__}: {exc}"[:200],
        ) from exc

    return OcrResponse(
        engine=chosen,
        text=text.strip(),
        ms=int((time.perf_counter() - started) * 1000),
    )

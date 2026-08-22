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
    available: list[str]
    detail: str


def _available() -> list[str]:
    import importlib.util

    engines = []
    if importlib.util.find_spec("pytesseract"):
        engines.append("tesseract")
    if importlib.util.find_spec("paddleocr") and importlib.util.find_spec("paddle"):
        engines.append("paddleocr")
    return engines


def _read_tesseract(data: bytes) -> str:
    import pytesseract
    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        return pytesseract.image_to_string(img)


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
    engines = _available()
    if DEFAULT_ENGINE not in engines:
        return HealthResponse(
            status="unhealthy",
            engine=DEFAULT_ENGINE,
            available=engines,
            detail=f"{DEFAULT_ENGINE} is not installed",
        )
    try:
        READERS[DEFAULT_ENGINE](_probe_image())
    except Exception as exc:  # noqa: BLE001 - a probe reports, it does not raise
        return HealthResponse(
            status="unhealthy",
            engine=DEFAULT_ENGINE,
            available=engines,
            detail=f"{type(exc).__name__}: {exc}"[:200],
        )
    return HealthResponse(
        status="ok", engine=DEFAULT_ENGINE, available=engines, detail="inference ok"
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

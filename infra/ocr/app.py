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
import shutil
import subprocess
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
    if shutil.which("tesseract"):
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
    img = _prepare(data)
    try:
        png = io.BytesIO()
        img.save(png, format="PNG")
        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l",
             os.environ.get("OCR_LANGUAGES", "eng+hin+mar")],
            input=png.getvalue(), capture_output=True, check=True, timeout=120,
        )
        return result.stdout.decode("utf-8")
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


# ---------------------------------------------------------------------------
# CLIP. Searching a document by what it looks like.
#
# Some documents have no text at all. A photo of people yields an empty OCR string, so
# no chunk and no vector are created, and the file is not ranked badly - it is absent.
# Three files in the corpus are in that state, and hero query 7 has no path without this.
#
# Local on purpose. Sending the image to a hosted vision model would break architectural
# rule 1 outright, because at layer one the image IS the document - and the masking
# pipeline, which exists to stop identifier text leaving, would be bypassed entirely by
# shipping a picture of the identifier instead.
# ---------------------------------------------------------------------------

CLIP_MODEL = os.environ.get("CLIP_MODEL", "ViT-B-32")
CLIP_WEIGHTS = os.environ.get("CLIP_WEIGHTS", "laion2b_s34b_b79k")

_clip: dict[str, object] = {}


class EmbedResponse(BaseModel):
    model: str
    dims: int
    embedding: list[float]
    ms: int


def _load_clip():
    """Loaded once, lazily. The weights are baked into the image, so this touches no
    network - a service that reaches nothing at runtime is part of the privacy claim."""
    if "model" not in _clip:
        import open_clip
        import torch

        torch.set_num_threads(max(1, (os.cpu_count() or 2) // 2))
        model, _, preprocess = open_clip.create_model_and_transforms(
            CLIP_MODEL, pretrained=CLIP_WEIGHTS
        )
        model.eval()
        _clip["model"] = model
        _clip["preprocess"] = preprocess
        _clip["tokenizer"] = open_clip.get_tokenizer(CLIP_MODEL)
    return _clip


def _normalise(vector) -> list[float]:
    """Unit-length, so cosine distance in pgvector is a dot product and comparable."""
    return (vector / vector.norm(dim=-1, keepdim=True)).squeeze(0).tolist()


@app.post("/embed/image", response_model=EmbedResponse)
async def embed_image(file: Annotated[UploadFile, File(...)]) -> EmbedResponse:
    import torch

    data = await file.read()
    started = time.perf_counter()
    clip = _load_clip()
    try:
        # Reuse _prepare: EXIF rotation and mode conversion matter here too, and a
        # sideways photo embeds as a sideways photo.
        image = _prepare(data)
        try:
            tensor = clip["preprocess"](image).unsqueeze(0)
        finally:
            image.close()
        with torch.no_grad():
            vector = clip["model"].encode_image(tensor)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{type(exc).__name__}: {exc}"[:200]
        ) from exc

    embedding = _normalise(vector)
    return EmbedResponse(
        model=f"{CLIP_MODEL}/{CLIP_WEIGHTS}",
        dims=len(embedding),
        embedding=embedding,
        ms=int((time.perf_counter() - started) * 1000),
    )


class TextEmbedRequest(BaseModel):
    text: str


@app.post("/embed/text", response_model=EmbedResponse)
async def embed_text(payload: TextEmbedRequest) -> EmbedResponse:
    """The query side of the shared space.

    CLIP embeds text and images into ONE space, which is what lets "the group photo"
    match a photo of a group with no text in it anywhere.
    """
    import torch

    started = time.perf_counter()
    clip = _load_clip()
    try:
        tokens = clip["tokenizer"]([payload.text])
        with torch.no_grad():
            vector = clip["model"].encode_text(tokens)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{type(exc).__name__}: {exc}"[:200]
        ) from exc

    embedding = _normalise(vector)
    return EmbedResponse(
        model=f"{CLIP_MODEL}/{CLIP_WEIGHTS}",
        dims=len(embedding),
        embedding=embedding,
        ms=int((time.perf_counter() - started) * 1000),
    )

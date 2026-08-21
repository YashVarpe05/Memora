"""OCR engines under test.

Every engine is optional. An engine that is not installed is reported as unavailable
and skipped - it never aborts the run, because the interesting comparison is usually
between the two you did manage to install.

Imports are lazy on purpose. paddleocr pulls in paddlepaddle, which is a large and
platform-fussy install, and importing it at module load would make the test suite
depend on it.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

NEWLINE = chr(10)


@dataclass(frozen=True)
class Availability:
    ok: bool
    detail: str


class OcrEngine(ABC):
    """One OCR backend. `read` returns the raw transcript; normalization happens later."""

    name: str

    @abstractmethod
    def availability(self) -> Availability:
        """Cheap check. Must not import heavy dependencies or make network calls."""

    @abstractmethod
    def read(self, image: Path) -> str: ...


def _installed(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


class TesseractEngine(OcrEngine):
    name = "tesseract"

    def availability(self) -> Availability:
        if not _installed("pytesseract"):
            return Availability(False, "pip package 'pytesseract' not installed")
        if shutil.which("tesseract") is None:
            return Availability(False, "tesseract binary not on PATH")
        return Availability(True, "ready")

    def read(self, image: Path) -> str:
        import pytesseract
        from PIL import Image

        with Image.open(image) as img:
            return pytesseract.image_to_string(img)


class PaddleEngine(OcrEngine):
    name = "paddleocr"

    def __init__(self, lang: str = "en") -> None:
        self._lang = lang
        self._ocr = None

    def availability(self) -> Availability:
        if not _installed("paddleocr"):
            return Availability(False, "pip package 'paddleocr' not installed")
        if not _installed("paddle"):
            return Availability(False, "paddlepaddle not installed")
        return Availability(True, "ready")

    def read(self, image: Path) -> str:
        if self._ocr is None:
            from paddleocr import PaddleOCR

            # Model download happens on first construction, not per image.
            # 3.x renamed use_angle_cls and dropped show_log; 2.x has neither of
            # the new names. Try new first and fall back, rather than pinning a
            # major version the team may not be able to install.
            try:
                self._ocr = PaddleOCR(
                    lang=self._lang,
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
            except (TypeError, ValueError):
                self._ocr = PaddleOCR(use_angle_cls=True, lang=self._lang)

        if hasattr(self._ocr, 'predict'):
            texts: list[str] = []
            for page in self._ocr.predict(str(image)) or []:
                got = page.get('rec_texts') if hasattr(page, 'get') else None
                if got:
                    texts.extend(got)
            if texts:
                return NEWLINE.join(texts)

        result = self._ocr.ocr(str(image))
        if not result or not result[0]:
            return ''
        return NEWLINE.join(line[1][0] for line in result[0])




class GeminiEngine(OcrEngine):
    """Gemini Flash vision. Costs money per image, so the caller opts in explicitly."""

    name = "gemini-flash"

    PROMPT = (
        "Transcribe all text in this image exactly as it appears. "
        "Preserve line breaks and reading order. "
        "Output only the transcript, with no commentary, headings, or markdown fences. "
        "If the image contains no text, output nothing."
    )

    def __init__(self, model: str | None = None) -> None:
        self._model = model or os.environ.get("GEMINI_OCR_MODEL", "gemini-2.0-flash")
        self._client = None

    def availability(self) -> Availability:
        if not _installed("google.genai"):
            return Availability(False, "pip package 'google-genai' not installed")
        if not os.environ.get("GEMINI_API_KEY"):
            return Availability(False, "GEMINI_API_KEY not set")
        return Availability(True, f"ready ({self._model})")

    def read(self, image: Path) -> str:
        from google import genai
        from google.genai import types

        if self._client is None:
            self._client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

        suffix = image.suffix.lower().lstrip(".")
        mime = "image/jpeg" if suffix in {"jpg", "jpeg"} else f"image/{suffix}"

        response = self._client.models.generate_content(
            model=self._model,
            contents=[
                types.Part.from_bytes(data=image.read_bytes(), mime_type=mime),
                self.PROMPT,
            ],
        )
        return response.text or ""


ENGINES: dict[str, type[OcrEngine]] = {
    TesseractEngine.name: TesseractEngine,
    PaddleEngine.name: PaddleEngine,
    GeminiEngine.name: GeminiEngine,
}

"""OCR client.

The engine runs in a container - see infra/ocr. That is the production ingestion
environment, and it is also the only place paddleocr runs at all, since it dies in a
oneDNN kernel on Windows.

Behind a protocol so tests never make a network call.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from memora.config import get_settings


class OcrUnavailable(RuntimeError):
    """The OCR service could not be reached or could not read the image."""


class OcrClient(Protocol):
    async def read(self, data: bytes, filename: str = "upload") -> str: ...


class HttpOcrClient:
    def __init__(self, base_url: str, engine: str | None = None, timeout: float = 120.0):
        self._base_url = base_url.rstrip("/")
        self._engine = engine
        self._timeout = timeout

    async def read(self, data: bytes, filename: str = "upload") -> str:
        params = {"engine": self._engine} if self._engine else None
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/ocr",
                    files={"file": (filename, data)},
                    params=params,
                )
        except httpx.HTTPError as exc:
            raise OcrUnavailable(f"OCR service unreachable: {exc}") from exc

        if response.status_code != 200:
            raise OcrUnavailable(f"OCR service returned {response.status_code}")
        return str(response.json().get("text", ""))


def build_ocr_client() -> OcrClient:
    settings = get_settings()
    return HttpOcrClient(base_url=settings.ocr_url, engine=settings.ocr_engine)

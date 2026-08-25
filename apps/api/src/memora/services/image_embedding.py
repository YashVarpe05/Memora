"""CLIP client. Embeds images and text into one shared space.

Runs in the same container as OCR — see infra/ocr. Local on purpose, and that is a
privacy property rather than a deployment convenience: at layer one the image IS the
document, so sending it to a hosted vision model would break architectural rule 1
outright. The masking pipeline exists to stop identifier *text* leaving; shipping a
photograph of the identifier would walk straight past it.

Behind a protocol so tests never make a network call.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from memora.config import get_settings


class ImageEmbeddingUnavailable(RuntimeError):
    """CLIP could not be reached or could not embed the input."""


class ImageEmbedder(Protocol):
    async def embed_image(self, data: bytes, filename: str = "upload") -> tuple[list[float], str]:
        """Returns (vector, model). The model name is stored per row so a change is visible."""
        ...

    async def embed_text(self, text: str) -> tuple[list[float], str]: ...


class HttpImageEmbedder:
    def __init__(self, base_url: str, timeout: float = 120.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def _call(self, path: str, **kwargs) -> tuple[list[float], str]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(f"{self._base_url}{path}", **kwargs)
        except httpx.HTTPError as exc:
            raise ImageEmbeddingUnavailable(f"CLIP service unreachable: {exc}") from exc

        if response.status_code != 200:
            raise ImageEmbeddingUnavailable(
                f"CLIP service returned {response.status_code}: {response.text[:200]}"
            )
        body = response.json()
        return body["embedding"], body["model"]

    async def embed_image(self, data: bytes, filename: str = "upload") -> tuple[list[float], str]:
        return await self._call("/embed/image", files={"file": (filename, data)})

    async def embed_text(self, text: str) -> tuple[list[float], str]:
        return await self._call("/embed/text", json={"text": text})


def build_image_embedder() -> ImageEmbedder:
    return HttpImageEmbedder(get_settings().ocr_url)

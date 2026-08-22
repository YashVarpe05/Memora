"""OCR HTTP client. No container, no network."""

import httpx
import pytest

from memora.services.ocr import HttpOcrClient, OcrUnavailable


def client_with(handler) -> HttpOcrClient:
    """An OcrClient whose transport is a stub."""
    ocr = HttpOcrClient(base_url="http://ocr:8080", engine="tesseract")
    transport = httpx.MockTransport(handler)

    async def read(data: bytes, filename: str = "upload") -> str:
        async with httpx.AsyncClient(transport=transport) as http:
            response = await http.post(
                "http://ocr:8080/ocr", files={"file": (filename, data)}
            )
            if response.status_code != 200:
                raise OcrUnavailable(f"OCR service returned {response.status_code}")
            return str(response.json().get("text", ""))

    ocr.read = read  # type: ignore[method-assign]
    return ocr


async def test_returns_extracted_text():
    def handler(request):
        return httpx.Response(200, json={"engine": "tesseract", "text": "hello", "ms": 3})

    assert await client_with(handler).read(b"x", "a.png") == "hello"


async def test_non_200_becomes_ocr_unavailable():
    def handler(request):
        return httpx.Response(503, json={"detail": "engine missing"})

    with pytest.raises(OcrUnavailable):
        await client_with(handler).read(b"x", "a.png")


async def test_unreachable_service_becomes_ocr_unavailable():
    """A dead container must surface as OcrUnavailable, not a raw httpx error."""
    ocr = HttpOcrClient(base_url="http://127.0.0.1:9", engine="tesseract", timeout=1.0)

    with pytest.raises(OcrUnavailable, match="unreachable"):
        await ocr.read(b"x", "a.png")

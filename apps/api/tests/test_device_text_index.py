"""A device that extracted its own text indexes it without sending the file."""

import hashlib
import uuid

from memora.db.models.chunk import Chunk
from memora.repositories.chunk import ChunkRepository


def _payload(text: str, *, name: str = "2344646563rt.pdf", path: str = "phone/Download/a.pdf"):
    return {
        "content_hash": hashlib.sha256(text.encode()).hexdigest(),
        "filename": name,
        "device_path": path,
        "mime_type": "application/pdf",
        "byte_size": 1234,
        "pages": [{"number": 1, "text": text}],
    }


async def test_text_is_indexed_masked_and_searchable_without_a_file(api, db, test_user_id):
    body = _payload("Electricity bill for March. Consumer address 12 MG Road Pune. PAN ABCDE1234F")
    response = await api.post("/index/text-jobs", json=body)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["deduplicated"] is False and result["chunks"] >= 1
    assert result["identifiers_masked"] >= 1
    memory_id = uuid.UUID(result["memory_id"])

    repo = ChunkRepository(db, test_user_id)
    chunks = (await db.execute(repo.scoped().where(Chunk.memory_id == memory_id))).scalars().all()
    assert chunks and all("ABCDE1234F" not in c.text for c in chunks)

    # No bytes were ever received, so the server cannot serve the original.
    assert (await api.get(f"/memories/{memory_id}/file")).status_code == 410

    found = await api.post("/search", json={"query": "electricity bill"})
    assert found.status_code == 200, found.text
    assert found.json()["results"][0]["memory_id"] == str(memory_id)
    assert found.json()["results"][0]["filename"] == "2344646563rt.pdf"


async def test_the_same_document_from_another_path_is_deduplicated(api):
    text = "Fee receipt. College of Engineering. Semester 5 tuition paid."
    first = await api.post("/index/text-jobs", json=_payload(text))
    second = await api.post(
        "/index/text-jobs", json=_payload(text, name="copy.pdf", path="phone/Documents/b.pdf")
    )
    assert first.status_code == second.status_code == 201
    assert second.json()["deduplicated"] is True
    assert second.json()["memory_id"] == first.json()["memory_id"]


async def test_a_document_with_no_text_is_rejected(api):
    response = await api.post("/index/text-jobs", json=_payload("   \n  "))
    assert response.status_code == 422
    assert "No text" in response.json()["detail"]


async def test_the_request_is_validated(api):
    bad_hash = {**_payload("some text"), "content_hash": "not-a-hash"}
    assert (await api.post("/index/text-jobs", json=bad_hash)).status_code == 422
    no_path = {**_payload("some text"), "device_path": ""}
    assert (await api.post("/index/text-jobs", json=no_path)).status_code == 422
    no_pages = {**_payload("some text"), "pages": []}
    assert (await api.post("/index/text-jobs", json=no_pages)).status_code == 422


async def test_oversized_extracted_text_is_refused(api):
    page = {"number": 1, "text": "x" * 200_000}
    body = {**_payload("seed"), "pages": [{**page, "number": n} for n in range(1, 4)]}
    assert (await api.post("/index/text-jobs", json=body)).status_code == 413

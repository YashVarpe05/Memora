"""Serving and erasing stored documents.

PRODUCT.md claims deletion removes rows, vectors and files, and that this is
demonstrable. These check it on disk rather than taking the 204 at face value.
"""

import uuid

from sqlalchemy import text as sql

from support import make_pdf, make_png


async def upload_png(api, doubles, name: str = "shot.png") -> dict:
    doubles["ocr"].text = "GOVERNMENT OF INDIA\nName: Test User"
    response = await api.post("/uploads", files={"file": (name, make_png(), "image/png")})
    assert response.status_code == 201, response.text
    return response.json()


async def test_uploaded_bytes_come_back_byte_identical(api, doubles):
    original = make_png(120, 90)
    doubles["ocr"].text = "some text"

    created = await api.post("/uploads", files={"file": ("a.png", original, "image/png")})
    memory_id = created.json()["memory_id"]

    fetched = await api.get(f"/memories/{memory_id}/file")

    assert fetched.status_code == 200
    assert fetched.content == original
    assert "attachment" in fetched.headers["content-disposition"]
    assert fetched.headers["x-content-type-options"] == "nosniff"


async def test_thumbnail_is_served_for_an_image(api, doubles):
    body = await upload_png(api, doubles)

    response = await api.get(f"/memories/{body['memory_id']}/thumbnail")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:3] == bytes([0xFF, 0xD8, 0xFF])


async def test_thumbnail_is_served_for_a_pdf(api):
    created = await api.post(
        "/uploads",
        files={"file": ("doc.pdf", make_pdf(["hello world"]), "application/pdf")},
    )
    assert created.status_code == 201, created.text

    response = await api.get(f"/memories/{created.json()['memory_id']}/thumbnail")

    assert response.status_code == 200
    assert response.content[:3] == bytes([0xFF, 0xD8, 0xFF])


async def test_a_memory_you_do_not_own_is_not_served(api):
    for suffix in ("file", "thumbnail"):
        response = await api.get(f"/memories/{uuid.uuid4()}/{suffix}")
        assert response.status_code == 404


async def test_identical_bytes_deduplicate_for_the_same_owner(api, doubles):
    first = await upload_png(api, doubles, "one.png")
    second = await upload_png(api, doubles, "two.png")

    assert second["deduplicated"] is True
    assert second["memory_id"] == first["memory_id"]


async def test_delete_removes_rows_vectors_and_the_file(api, db, doubles, blob_store):
    body = await upload_png(api, doubles)
    memory_id = body["memory_id"]

    stored = await db.execute(
        sql("SELECT content_hash FROM memories WHERE id = :i"), {"i": memory_id}
    )
    content_hash = stored.scalar_one()
    owner = (await db.execute(sql("SELECT user_id FROM memories WHERE id = :i"),
                              {"i": memory_id})).scalar_one()
    assert blob_store.path(owner, content_hash).exists()

    response = await api.delete(f"/memories/{memory_id}")
    assert response.status_code == 204

    rows = await db.execute(sql("SELECT count(*) FROM memories WHERE id = :i"), {"i": memory_id})
    assert rows.scalar_one() == 0

    vectors = await db.execute(
        sql("SELECT count(*) FROM chunks WHERE memory_id = :i"), {"i": memory_id}
    )
    assert vectors.scalar_one() == 0, "vectors survived the delete"

    assert not blob_store.path(owner, content_hash).exists(), "the file survived on disk"
    assert not blob_store.thumbnail_path(owner, content_hash).exists()


async def test_deleting_a_memory_you_do_not_own_is_a_404(api):
    assert (await api.delete(f"/memories/{uuid.uuid4()}")).status_code == 404


async def test_pdf_chunks_carry_their_page(api, db):
    created = await api.post(
        "/uploads",
        files={
            "file": (
                "two.pdf",
                make_pdf(["first page words here", "second page words here"]),
                "application/pdf",
            )
        },
    )
    assert created.status_code == 201, created.text

    pages = await db.execute(
        sql("SELECT page FROM chunks WHERE memory_id = :i ORDER BY ordinal"),
        {"i": created.json()["memory_id"]},
    )
    values = [row[0] for row in pages]

    assert values, "expected at least one chunk"
    assert all(v is not None for v in values), "a PDF chunk must know its page"


async def test_image_chunks_have_no_page(api, doubles, db):
    body = await upload_png(api, doubles)

    pages = await db.execute(
        sql("SELECT page FROM chunks WHERE memory_id = :i"), {"i": body["memory_id"]}
    )

    assert all(row[0] is None for row in pages)

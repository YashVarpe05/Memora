"""POST /uploads - PDF in, chunks stored."""

from support import make_pdf, make_png


async def test_pdf_upload_stores_chunks(api):
    pdf = make_pdf(["Retrieval is two stages. " * 60], title="Memora Notes")

    response = await api.post(
        "/uploads", files={"file": ("notes.pdf", pdf, "application/pdf")}
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "Memora Notes"
    assert body["chunks"] >= 1
    assert body["memory_id"]


async def test_non_pdf_is_rejected_by_content_not_extension(api):
    """A .pdf extension is a claim. The magic bytes are the evidence."""
    response = await api.post(
        "/uploads",
        files={"file": ("lies.pdf", b"MZ this is a windows binary", "application/pdf")},
    )

    assert response.status_code == 415


async def test_pdf_with_no_text_anywhere_is_rejected(api, doubles):
    """No text layer and OCR finds nothing either - there is nothing to index."""
    doubles["ocr"].text = ""
    empty = make_pdf([""], title="Blank")

    response = await api.post(
        "/uploads", files={"file": ("blank.pdf", empty, "application/pdf")}
    )

    assert response.status_code == 422


async def test_pdf_without_a_text_layer_falls_back_to_ocr(api, doubles):
    """The mail.pdf case: a printed email whose pages are images.

    Before this path existed the document was permanently unfindable, which is the
    exact failure the product exists to fix.
    """
    doubles["ocr"].text = "From: hr@company.com" + chr(10) + "Subject: Offer letter"
    scanned = make_pdf([""], title="Scanned Mail")

    response = await api.post(
        "/uploads", files={"file": ("mail.pdf", scanned, "application/pdf")}
    )

    assert response.status_code == 201, response.text
    assert response.json()["chunks"] >= 1
    assert doubles["ocr"].calls, "OCR should have been used for a PDF with no text layer"


async def test_embedder_receives_the_contextual_prefix(api, doubles):
    pdf = make_pdf(["Alpha beta gamma. " * 60], title="Prefixed Doc")

    await api.post("/uploads", files={"file": ("d.pdf", pdf, "application/pdf")})

    embedded = doubles["embedder"].calls[0]
    assert all(text.startswith("Prefixed Doc") for text in embedded)


async def test_image_upload_is_ocred_and_stored(api, doubles):
    """The flagship path: a photo with no text layer becomes searchable."""
    doubles["ocr"].text = "GOVERNMENT OF INDIA\nName: Test User\nDOB: 01/01/2000"

    response = await api.post(
        "/uploads", files={"file": ("aadhaar.png", make_png(), "image/png")}
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["source_type"] == "image"
    assert body["chunks"] >= 1
    assert doubles["ocr"].calls == ["aadhaar.png"]


async def test_image_with_no_text_is_rejected(api, doubles):
    doubles["ocr"].text = ""

    response = await api.post(
        "/uploads", files={"file": ("blank.png", make_png(), "image/png")}
    )

    assert response.status_code == 422
    assert "No text found" in response.json()["detail"]


async def test_image_upload_fails_loudly_when_ocr_is_down(api, app, doubles):
    """Silently storing an un-OCR'd image would make it permanently unfindable."""
    from memora.api.routers import uploads as uploads_router

    from support import BrokenOcr

    app.dependency_overrides[uploads_router.get_ocr] = BrokenOcr

    response = await api.post(
        "/uploads", files={"file": ("x.png", make_png(), "image/png")}
    )

    assert response.status_code == 503


async def test_aadhaar_in_an_image_is_masked_before_storage(api, db, doubles):
    """End to end: OCR text carrying an identifier never reaches the database."""
    from sqlalchemy import text as sql

    from test_masking import aadhaar

    number = aadhaar("23456789012")
    doubles["ocr"].text = f"GOVERNMENT OF INDIA\nAadhaar {number}\nName: Test User"

    response = await api.post(
        "/uploads", files={"file": ("id.png", make_png(), "image/png")}
    )
    assert response.status_code == 201, response.text
    assert response.json()["identifiers_masked"] >= 1

    found = await db.execute(sql("SELECT count(*) FROM chunks WHERE text LIKE :n"),
                             {"n": f"%{number}%"})
    assert found.scalar_one() == 0, "the identifier reached the database"

    embedded = " ".join(t for call in doubles["embedder"].calls for t in call)
    assert number not in embedded, "the identifier reached the embedder"

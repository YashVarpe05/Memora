"""POST /uploads - PDF in, chunks stored."""

from support import make_pdf


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


async def test_pdf_with_no_text_is_rejected_not_stored_empty(api):
    empty = make_pdf([""], title="Blank")

    response = await api.post(
        "/uploads", files={"file": ("blank.pdf", empty, "application/pdf")}
    )

    assert response.status_code == 422
    assert "OCR" in response.json()["detail"]


async def test_embedder_receives_the_contextual_prefix(api, doubles):
    pdf = make_pdf(["Alpha beta gamma. " * 60], title="Prefixed Doc")

    await api.post("/uploads", files={"file": ("d.pdf", pdf, "application/pdf")})

    embedded = doubles["embedder"].calls[0]
    assert all(text.startswith("Prefixed Doc") for text in embedded)

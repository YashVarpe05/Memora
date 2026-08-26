"""Finding a document by what it looks like, end to end.

Hero query 7 — "the group photo" — has no text-pipeline path at any quality. OCR returns
an empty string, so no chunk and no vector are created, and the file is not ranked badly:
it is absent. Three corpus files are in that state.

These tests cover the path from ingest to a fused search result. `test_fusion.py` covers
the ranking arithmetic in isolation; this covers that the two are actually connected,
which is the part that was silently broken — the search router has its own CLIP dependency
and it was not overridden, so every test exercised the "CLIP unavailable" branch while
appearing to pass.
"""

from support import FakeImageEmbedder, make_png


async def upload_photo(api, doubles, *, name: str, ocr_text: str = "") -> str:
    """A photo with no readable text, which is the case that matters."""
    doubles["ocr"].text = ocr_text
    response = await api.post("/uploads", files={"file": (name, make_png(), "image/png")})
    assert response.status_code == 201, response.text
    return response.json()["memory_id"]


async def test_a_text_free_photo_is_findable(api, doubles):
    """The whole point. Before CLIP this document could not be ingested at all."""
    memory_id = await upload_photo(api, doubles, name="group.png")

    body = (await api.post("/search", json={"query": "group.png"})).json()

    assert not body["refused"]
    assert memory_id in [r["memory_id"] for r in body["results"]], (
        "a photo with no text was not findable, so visual search is not connected"
    )


async def test_an_image_only_result_carries_no_chunk(api, doubles):
    """A photo with no text has no chunk to point at, and the response must say so
    rather than inventing one."""
    memory_id = await upload_photo(api, doubles, name="group.png")

    body = (await api.post("/search", json={"query": "group.png"})).json()
    hit = next(r for r in body["results"] if r["memory_id"] == memory_id)

    assert hit["matched_chunk_id"] is None
    assert hit["snippet"] == "", "there is no text; a snippet would be fabricated"


async def test_disabling_images_removes_the_photo(api, doubles):
    """The ablation switch. Without it the visual arm cannot be measured against the
    text-only numbers every report before it recorded."""
    memory_id = await upload_photo(api, doubles, name="group.png")

    body = (
        await api.post("/search", json={"query": "group.png", "images": False})
    ).json()

    assert memory_id not in [r["memory_id"] for r in body["results"]], (
        "images:false must exclude the visual list entirely"
    )


async def test_clip_being_down_does_not_break_a_text_search(api, doubles, app):
    """Degrade, do not fail. A text query the chunk index can answer must still work."""
    from memora.api.routers import search as search_router

    doubles["ocr"].text = "government of india aadhaar identity document"
    await api.post("/uploads", files={"file": ("id.png", make_png(), "image/png")})

    app.dependency_overrides[search_router.get_image_embedder] = lambda: FakeImageEmbedder(
        fails=True
    )
    body = (
        await api.post("/search", json={"query": "the aadhaar identity document"})
    ).json()

    assert body["results"], "visual search being down must not stop text retrieval"


async def test_a_document_found_by_both_lists_outranks_one_found_by_either(api, doubles):
    """The ID-card case: OCR catches a few words AND it looks like a card.

    Agreement between the two lists is the signal RRF exists to reward.
    """
    both = await upload_photo(
        api, doubles, name="card.png", ocr_text="government of india identity card"
    )
    await upload_photo(api, doubles, name="unrelated.png", ocr_text="")

    body = (
        await api.post("/search", json={"query": "government of india identity card"})
    ).json()

    assert body["results"][0]["memory_id"] == both, (
        "a document matching on text and picture must outrank one matching on picture alone"
    )

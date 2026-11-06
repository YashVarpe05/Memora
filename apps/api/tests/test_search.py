"""POST /search - ranked documents, not chunks.

Queries here deliberately carry a filterable signal - a source type, a sender, or a date
- so the stage 1 path actually executes. Earlier versions used strings like "dashboard"
and "anything", which query_signal correctly skips, so 72% of these tests measured the
dense-only path while appearing to cover two-stage retrieval. The heuristic was right;
the queries were not the kind a person types. Found with `pytest --double-usage`.

Signal words, not filler. FakeEmbedder is bag-of-words and normalises by vector length,
so "the photo of my aadhaar card" scores 0.365 against a document "aadhaar card ..."
while "the scanned aadhaar card" scores 0.447 - padding a query with articles pushes it
under MIN_SIMILARITY_UNCALIBRATED. Real embedders do not degrade that way, so a failure
of that kind here is a limit of the double rather than a defect in retrieval.
"""

from support import make_pdf, make_png

LONG = "the annual fee receipt for semester seven payment confirmation reference "


async def upload_pdf(api, pages: list[str], name: str, title: str = "Doc") -> str:
    response = await api.post(
        "/uploads", files={"file": (name, make_pdf(pages, title=title), "application/pdf")}
    )
    assert response.status_code == 201, response.text
    return response.json()["memory_id"]


async def upload_image(api, doubles, text: str, name: str) -> str:
    doubles["ocr"].text = text
    response = await api.post("/uploads", files={"file": (name, make_png(), "image/png")})
    assert response.status_code == 201, response.text
    return response.json()["memory_id"]


async def test_one_document_with_many_matching_chunks_is_one_result(api):
    """The whole point of layer one: results are documents, not chunks."""
    memory_id = await upload_pdf(api, [LONG * 40], "long.pdf", title="Fee Receipt")

    response = await api.post("/search", json={"query": LONG.strip()})

    assert response.status_code == 200, response.text
    body = response.json()
    ids = [r["memory_id"] for r in body["results"]]
    assert ids.count(memory_id) == 1, "a document appeared more than once"


async def test_results_are_ranked_and_numbered_from_one(api, doubles):
    await upload_image(api, doubles, "aadhaar government of india identity", "id.png")
    await upload_pdf(api, ["completely unrelated content about databases"], "db.pdf")

    body = (await api.post("/search", json={"query": "the scanned aadhaar identity card"})).json()

    assert [r["rank"] for r in body["results"]] == list(range(1, len(body["results"]) + 1))
    scores = [r["score"] for r in body["results"]]
    assert scores == sorted(scores, reverse=True)


async def test_result_carries_what_a_card_needs(api, doubles):
    memory_id = await upload_image(api, doubles, "government of india aadhaar", "id.png")

    body = (
        await api.post("/search", json={"query": "the scanned government aadhaar document"})
    ).json()
    top = body["results"][0]

    assert top["memory_id"] == memory_id
    assert top["filename"] == "id.png"
    assert top["source_type"] == "image"
    assert top["snippet"]
    assert top["matched_chunk_id"]
    assert top["byte_size"] > 0
    assert top["file_url"] == f"/memories/{memory_id}/file"
    assert top["thumbnail_url"] == f"/memories/{memory_id}/thumbnail"


async def test_pdf_result_carries_the_page(api):
    """Click-through should open on the match, not on page one."""
    await upload_pdf(
        api,
        ["cover page", "the reimbursement policy details are on this page"],
        "policy.pdf",
    )

    body = (
        await api.post("/search", json={"query": "the pdf about reimbursement policy details"})
    ).json()

    assert body["results"], "expected a match"
    assert body["results"][0]["page"] is not None


async def test_image_result_has_no_page(api, doubles):
    await upload_image(api, doubles, "a screenshot of something", "shot.png")

    body = (await api.post("/search", json={"query": "the screenshot of something"})).json()

    assert body["results"][0]["page"] is None


async def test_empty_corpus_refuses(api):
    body = (await api.post("/search", json={"query": "the scanned anything"})).json()

    assert body["refused"] is True
    assert body["reason"] == "no_evidence"
    assert body["results"] == []


async def test_limit_is_respected(api, doubles):
    for i in range(4):
        await upload_image(api, doubles, f"document number {i} about invoices", f"{i}.png")

    body = (await api.post("/search", json={"query": "the pdf invoices", "limit": 2})).json()

    assert len(body["results"]) <= 2


async def test_blank_query_is_rejected(api):
    assert (await api.post("/search", json={"query": ""})).status_code == 422


async def test_limit_above_the_cap_is_rejected(api):
    assert (await api.post("/search", json={"query": "x", "limit": 500})).status_code == 422


async def test_window_size_is_reported(api, doubles):
    """The over-fetch bound is observable rather than theoretical."""
    await upload_image(api, doubles, "one about receipts", "a.png")
    await upload_image(api, doubles, "another about receipts", "b.png")

    body = (await api.post("/search", json={"query": "the scanned receipts document"})).json()

    assert body["documents_in_window"] >= 1


async def test_snippets_never_show_an_identifier(api, doubles):
    """The stored chunk is masked, so a result card cannot leak one."""
    from test_masking import aadhaar

    number = aadhaar("23456789012")
    await upload_image(api, doubles, f"aadhaar card number {number} govt", "id.png")

    body = (await api.post("/search", json={"query": "the scanned aadhaar card"})).json()

    assert body["results"], "expected a match"
    assert all(number not in r["snippet"] for r in body["results"])
    assert "[AADHAAR_NUMBER]" in body["results"][0]["snippet"]


async def test_stage_one_is_consulted_and_reported(api, doubles):
    """The extracted filters come back in the response, so a result can be explained."""
    doubles["stage_one"].filters = {"source_types": ["image"]}
    await upload_image(api, doubles, "some text here", "a.png")

    body = (await api.post("/search", json={"query": "the screenshot"})).json()

    assert doubles["stage_one"].calls == ["the screenshot"]
    assert body["filters"] == {"source_types": ["image"]}
    assert body["stage1_ms"] is not None


async def test_stage_one_can_be_switched_off_for_the_ablation(api, doubles):
    await upload_image(api, doubles, "some text here", "a.png")

    body = (await api.post("/search", json={"query": "x", "stage1": False})).json()

    assert doubles["stage_one"].calls == []
    assert body["stage1_ms"] is None


async def test_a_matching_source_type_is_boosted_not_required(api, doubles):
    """The mail.pdf case: a filter is evidence, not truth.

    A document that mismatches the filter must still be reachable, because a scanned
    email has source_type pdf while the query calls it "the mail".
    """
    doubles["stage_one"].filters = {"source_types": ["email"]}
    await upload_pdf(api, ["the offer letter from human resources"], "scan.pdf")

    body = (await api.post("/search", json={"query": "the mail with the offer letter"})).json()

    assert body["results"], "a mismatching source type must not exclude the document"
    assert body["results"][0]["filename"] == "scan.pdf"


async def test_boosted_and_raw_scores_are_both_reported(api, doubles):
    doubles["stage_one"].filters = {"source_types": ["image"]}
    await upload_image(api, doubles, "dashboard with forms", "shot.png")

    # "screenshot" is what makes stage 1 run at all; a bare "dashboard" carries no
    # filterable signal and is skipped, so there would be no boost to report.
    top = (
        await api.post("/search", json={"query": "dashboard screenshot"})
    ).json()["results"][0]

    assert top["score"] > top["raw_score"], "a matching source type should boost"
    assert top["raw_score"] <= 1.0

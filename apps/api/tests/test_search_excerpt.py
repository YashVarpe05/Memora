"""Search previews expose the matching passage instead of always showing the heading."""

import pytest

from memora.services.lexical import excerpt


def test_excerpt_finds_late_match_and_keeps_whole_words():
    text = (
        "Introductory background. " * 35 + "Unique ZXKRAIL reference here. " + "More detail. " * 35
    )
    preview = excerpt(text, "ZXKRAIL", 100)
    assert "Unique ZXKRAIL reference here." in preview
    assert len(preview) <= 100
    assert preview.startswith("…") and preview.endswith("…")
    assert not preview.startswith("…roductory")


@pytest.mark.parametrize("term", ["गुणपत्रिका", "पावती", "CAFÉ"])
def test_excerpt_retains_unicode_words_and_case(term):
    text = "प्रस्तावना माहिती " * 50 + term + " संदर्भ तपशील " * 50
    assert term in excerpt(text, term.casefold(), 90)


def test_excerpt_normalizes_query_without_rewriting_original_text():
    text = "Introduction " * 50 + "cafe\u0301 invoice" + " details" * 50
    assert "cafe\u0301" in excerpt(text, "café", 70)


def test_unmatched_query_uses_readable_bounded_prefix():
    assert (
        excerpt("First sentence followed by additional words.", "missing", 24)
        == "First sentence followed…"
    )
    assert excerpt("Short text", "missing") == "Short text"
    assert excerpt("", "query") == ""


def test_plain_text_is_not_replaced_by_html_highlighting():
    assert (
        excerpt("Invoice <script>alert(1)</script>", "invoice")
        == "Invoice <script>alert(1)</script>"
    )


def test_oversized_token_is_bounded():
    assert len(excerpt("x" * 1000, "xxxxx", 50)) <= 50
    with pytest.raises(ValueError):
        excerpt("text", "query", 0)


async def test_late_chunk_match_selects_correct_pdf_page(api, app):
    from memora.api.routers.search import get_embedder

    from support import FakeEmbedder, make_pdf

    cover = "General project overview background information"
    # Newlines keep the actual PDF text inside the page instead of beyond its width.
    body = (
        "General introductory context before evidence.\n" * 10
        + "Unique reference ZXKRAIL is printed on this page."
    )
    uploaded = await api.post(
        "/uploads",
        files={
            "file": (
                "728495.pdf",
                make_pdf([cover, body]),
                "application/pdf",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text

    class CoverEmbedder(FakeEmbedder):
        async def embed(self, texts):
            return [self._vector(cover) for _ in texts]

    app.dependency_overrides[get_embedder] = CoverEmbedder
    response = await api.post("/search", json={"query": "ZXKRAIL", "images": False})
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["memory_id"] == uploaded.json()["memory_id"]
    assert result["page"] == 2
    assert "ZXKRAIL" in result["snippet"]


@pytest.mark.parametrize("query", ["mera adhaar", "मेरा आधार कार्ड", "माझे आधार कार्ड"])
@pytest.mark.parametrize("dense_cover", [False, True])
async def test_category_alias_opens_category_page_not_cover(api, app, query, dense_cover):
    from memora.api.routers.search import get_embedder

    from support import FakeEmbedder, make_pdf

    cover = "General project overview background information"
    uploaded = await api.post(
        "/uploads",
        files={
            "file": (
                "9284621.pdf",
                make_pdf([cover, "Aadhaar Unique Identification Authority of India"]),
                "application/pdf",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text

    class CoverEmbedder(FakeEmbedder):
        async def embed(self, texts):
            return [self._vector(cover) for _ in texts]

    app.dependency_overrides[get_embedder] = CoverEmbedder if dense_cover else lambda: None
    response = await api.post("/search", json={"query": query, "images": False})
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["memory_id"] == uploaded.json()["memory_id"]
    assert result["page"] == 2
    assert "Aadhaar" in result["snippet"]

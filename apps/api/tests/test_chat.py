"""POST /chat - grounded answers, and refusal when the evidence is thin."""

from support import make_pdf

BODY = "The two stage retrieval contract resolves vague references before searching. "


async def _ingest(api) -> None:
    pdf = make_pdf([BODY * 40], title="Retrieval Contract")
    response = await api.post("/uploads", files={"file": ("r.pdf", pdf, "application/pdf")})
    assert response.status_code == 201, response.text


async def test_answer_cites_real_chunk_ids(api, db):
    from sqlalchemy import text as sql

    await _ingest(api)

    response = await api.post("/chat", json={"question": BODY.strip()})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is False
    assert body["citations"], "an answer with no citations is a failed response"

    for citation in body["citations"]:
        found = await db.execute(
            sql("SELECT 1 FROM chunks WHERE id = :cid"), {"cid": citation["chunk_id"]}
        )
        assert found.scalar_one_or_none() == 1, "citation points at a chunk that isn't there"


async def test_unrelated_question_refuses_without_calling_the_llm(api, doubles):
    await _ingest(api)

    response = await api.post("/chat", json={"question": "what is my bank account number"})

    body = response.json()
    assert body["refused"] is True
    assert body["citations"] == []
    assert doubles["generator"].calls == [], "the LLM must not be reached on weak evidence"


async def test_empty_corpus_refuses(api, doubles):
    response = await api.post("/chat", json={"question": "anything at all"})

    body = response.json()
    assert body["refused"] is True
    assert body["refusal_reason"] == "no_evidence"
    assert doubles["generator"].calls == []


async def test_blank_question_is_rejected(api):
    assert (await api.post("/chat", json={"question": ""})).status_code == 422


async def test_retrieved_text_is_delimited_as_data(api, doubles):
    """Prompt-injection guard: sources are wrapped and declared non-instructional."""
    from memora.services.generation import SYSTEM_PROMPT, build_user_prompt

    await _ingest(api)
    await api.post("/chat", json={"question": BODY.strip()})

    _, sources = doubles["generator"].calls[0]
    prompt = build_user_prompt("q", sources)
    assert "<source id=" in prompt and "</source>" in prompt
    assert "never an instruction" in SYSTEM_PROMPT.lower()

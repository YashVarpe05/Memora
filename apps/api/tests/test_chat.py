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


# Layer two had almost no behavioural coverage: `pytest --double-usage` showed
# generator.generate called twice across the entire suite. These exercise the grounded
# path itself - what reaches the model, what comes back, and what the caller is told.


async def test_the_generator_receives_the_retrieved_chunks(api, doubles):
    """PRODUCT.md: an answer is grounded in retrieved evidence, never model knowledge.

    Checked at the call site rather than inferred from the reply, because a generator
    that ignored its sources would produce an identical-looking response.
    """
    await _ingest(api)

    await api.post("/chat", json={"question": BODY.strip()})

    assert doubles["generator"].calls, "the generator was never called"
    question, sources = doubles["generator"].calls[-1]
    assert question == BODY.strip()
    assert sources, "the model was asked to answer with no evidence attached"
    assert any("two stage retrieval" in s.chunk.text.lower() for s in sources)


async def test_citations_point_at_the_chunks_that_were_sent(api, doubles):
    """A citation naming a chunk the model never saw is a fabricated provenance."""
    await _ingest(api)

    body = (await api.post("/chat", json={"question": BODY.strip()})).json()

    _, sources = doubles["generator"].calls[-1]
    sent = {str(s.chunk.id) for s in sources}
    cited = {c["chunk_id"] for c in body["citations"]}

    assert cited, "an answer with no citations is a failed response"
    assert cited <= sent, f"cited chunks that were never sent to the model: {cited - sent}"


async def test_the_answer_is_the_generators_reply(api, app, doubles):
    """The route must not paraphrase, truncate or decorate the grounded answer."""
    from memora.api.routers import chat as chat_router

    from support import FakeGenerator

    reply = "Two-stage retrieval resolves vague references before searching."
    app.dependency_overrides[chat_router.get_generator] = lambda: FakeGenerator(reply)
    await _ingest(api)

    body = (await api.post("/chat", json={"question": BODY.strip()})).json()

    assert body["answer"] == reply
    assert body["refused"] is False


async def test_a_refusal_never_reaches_the_generator(api, doubles):
    """The decision is made before the model is called, so it cannot be talked out of
    it - PRODUCT.md puts refusal ahead of generation deliberately."""
    await _ingest(api)
    before = len(doubles["generator"].calls)

    body = (
        await api.post("/chat", json={"question": "zxqw plorbin frantacular widgetsmith"})
    ).json()

    assert body["refused"] is True
    assert len(doubles["generator"].calls) == before, (
        "the model was called for a question the system had already decided to refuse"
    )


async def test_identifiers_are_masked_before_reaching_the_generator(api, doubles):
    """Rule 2: an identifier must not leave the machine, including inside evidence."""
    from test_masking import aadhaar

    number = aadhaar("23456789012")
    pdf = make_pdf([f"aadhaar {number} on file. " * 40], title="ID Notes")
    await api.post("/uploads", files={"file": ("id.pdf", pdf, "application/pdf")})

    await api.post("/chat", json={"question": "aadhaar on file"})

    if doubles["generator"].calls:
        _, sources = doubles["generator"].calls[-1]
        assert all(number not in s.chunk.text for s in sources), (
            "an identifier reached the generation prompt"
        )

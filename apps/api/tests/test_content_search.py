"""Synthetic, non-personal acceptance fixtures for content-based document discovery."""

import io
import zipfile
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from memora.api.deps import CurrentUserDep, current_user_id, get_db
from memora.api.routers.pairing import get_store
from memora.repositories.index_job import IndexJobRepository
from memora.services.document_type import classify
from memora.services.extraction import DocumentError, extract_office_or_text, extract_pdf
from memora.services.pairing import PairingStore
from memora.services.rules_query_understanding import RulesQueryUnderstanding

from support import FakeOcr, make_pdf


@pytest.mark.parametrize(
    "query", ["my Aadhaar", "mera adhaar", "my adhaaar card", "मेरा आधार कार्ड", "माझे आधार कार्ड"]
)
async def test_random_filename_aadhaar_is_first(api, query):
    await api.post(
        "/uploads",
        files={
            "file": ("aadhaar.pdf", make_pdf(["Electricity bill March 2026"]), "application/pdf")
        },
    )
    answer = await api.post(
        "/uploads",
        files={
            "file": (
                "2344646563rt.pdf",
                make_pdf(
                    [
                        "Unique Identification Authority of India\n"
                        "Aadhaar card\nSynthetic test document"
                    ]
                ),
                "application/pdf",
            )
        },
    )
    assert answer.status_code == 201, answer.text
    response = await api.post("/search", json={"query": query, "images": False})
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["memory_id"] == answer.json()["memory_id"]
    assert result["document_type"] == "aadhaar"
    assert result["page"] == 1


def test_content_wins_over_misleading_filename():
    assert classify("aadhaar.pdf", "Electricity bill March 2026") == "bill"
    assert classify("2344646563rt.pdf", "Unique Identification Authority of India") == "aadhaar"


async def test_mixed_pdf_reads_scanned_page():
    import pymupdf

    with pymupdf.open(stream=make_pdf(["Cover page", ""]), filetype="pdf") as doc:
        data = doc.tobytes()
    ocr = FakeOcr("आधार Synthetic card")
    _, blocks = await extract_pdf(data, ocr, "234.pdf")
    assert ocr.calls == ["234.pdf#page2"]
    assert any("आधार" in b.text and b.page == 2 for b in blocks)


async def test_encrypted_pdf_is_actionable():
    import pymupdf

    with pymupdf.open(stream=make_pdf(["Secret"]), filetype="pdf") as doc:
        data = doc.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="password"
        )
    with pytest.raises(DocumentError, match="Password-protected"):
        await extract_pdf(data, FakeOcr(), "locked.pdf")


def test_docx_and_multilingual_text():
    content = "गुणपत्रिका Synthetic marksheet"
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'
            + content
            + "</w:t></w:r></w:p></w:body></w:document>",
        )
    assert content in extract_office_or_text(data.getvalue(), "123.docx").blocks[0].text
    assert content in extract_office_or_text(content.encode(), "123.txt").blocks[0].text


async def test_identity_persists_as_hashes_and_isolates_devices(tmp_path):
    path = str(tmp_path / "auth.sqlite")
    first = PairingStore(path)
    token_a = first.claim(first.start().code)
    token_b = first.claim(first.start().code)
    restarted = PairingStore(path)
    assert restarted.identity(token_a) == first.identity(token_a)
    assert restarted.identity(token_a) != restarted.identity(token_b)
    rows = restarted.db.execute("SELECT hash FROM devices").fetchall()
    assert all(token_a not in row and token_b not in row for row in rows)


async def test_authenticated_device_boundaries(api, app, db):
    pairings = PairingStore()
    a = pairings.claim(pairings.start().code)
    b = pairings.claim(pairings.start().code)
    app.dependency_overrides[get_store] = lambda: pairings
    app.dependency_overrides.pop(current_user_id)

    async def scope(user_id: CurrentUserDep):
        await db.execute(text("SELECT set_config('app.user_id', :id, true)"), {"id": str(user_id)})
        yield db

    app.dependency_overrides[get_db] = scope
    api.headers["Authorization"] = f"Bearer {a}"
    uploaded = await api.post(
        "/uploads", files={"file": ("123.pdf", make_pdf(["Aadhaar synthetic"]), "application/pdf")}
    )
    assert uploaded.status_code == 201, uploaded.text
    mid = uploaded.json()["memory_id"]
    queued = await api.post(
        "/index/jobs",
        data={"device_path": "content://test/1"},
        files={"file": ("456.txt", b"Synthetic receipt", "text/plain")},
    )
    assert queued.status_code == 202, queued.text
    jid = queued.json()["id"]
    api.headers["Authorization"] = f"Bearer {b}"
    for path in (
        f"/memories/{mid}/file",
        f"/memories/{mid}/thumbnail",
        f"/memories/{mid}/pages/1",
        f"/index/jobs/{jid}",
    ):
        assert (await api.get(path)).status_code == 404
    assert (await api.delete(f"/memories/{mid}")).status_code == 404
    assert (await api.post(f"/index/jobs/{jid}/retry")).status_code == 404
    assert (await api.get("/index/jobs")).json()["counts"] == {}
    assert (await api.post("/search", json={"query": "my Aadhaar", "images": False})).json()[
        "results"
    ] == []
    assert (await db.execute(text("SELECT * FROM index_jobs"))).all() == []
    assert (await db.execute(text("SELECT * FROM memories"))).all() == []
    api.headers["Authorization"] = f"Bearer {a}"
    file = await api.get(f"/memories/{mid}/file")
    assert file.status_code == 200
    assert file.headers["cache-control"] == "private, no-store"
    assert file.headers["vary"] == "Authorization"
    page = await api.get(f"/memories/{mid}/pages/1")
    assert page.status_code == 200 and page.headers["x-page-count"] == "1"
    assert (await api.get(f"/memories/{mid}/pages/2")).status_code == 404


async def test_durable_job_retries_without_reupload(
    api, db, test_user_id, doubles, blob_store, monkeypatch
):
    from memora import worker

    response = await api.post(
        "/index/jobs",
        data={"device_path": "content://test/1"},
        files={"file": ("123.txt", b"Aadhaar synthetic document", "text/plain")},
    )
    assert response.status_code == 202, response.text
    repeated = await api.post(
        "/index/jobs",
        data={"device_path": "content://test/1"},
        files={"file": ("123.txt", b"Aadhaar synthetic document", "text/plain")},
    )
    assert response.json()["id"] == repeated.json()["id"]

    async def scoped(_):
        yield db

    monkeypatch.setattr(worker, "scoped_session", scoped)
    deps = {k: doubles[k] for k in ("embedder", "counter", "ocr", "image_embedder")}
    deps["blobs"] = blob_store

    class Down:
        async def embed(self, _):
            raise RuntimeError("sensitive provider error")

    await worker.process_one(test_user_id, dependencies={**deps, "embedder": Down()})
    job = (await db.execute(IndexJobRepository(db, test_user_id).scoped())).scalar_one()
    assert job.status == "queued" and job.attempts == 1
    assert "sensitive" not in job.error
    job.retry_at = datetime.now(UTC)
    await worker.process_one(test_user_id, dependencies=deps)
    assert job.status == "completed" and job.attempts == 2
    found = await api.post("/search", json={"query": "mera adhaar", "images": False})
    assert found.json()["results"][0]["memory_id"] == job.result["memory_id"]
    assert (await api.delete(f"/memories/{job.result['memory_id']}")).status_code == 204
    assert (await api.get(f"/index/jobs/{job.id}")).status_code == 404


async def test_duplicate_locations_do_not_mark_remaining_copy_removed(api):
    data = make_pdf(["Aadhaar synthetic"])
    first = await api.post("/uploads", data={"device_path": "a"}, files={"file": ("1.pdf", data)})
    second = await api.post("/uploads", data={"device_path": "b"}, files={"file": ("2.pdf", data)})
    assert first.json()["memory_id"] == second.json()["memory_id"]
    response = await api.post("/device/reconcile", json={"paths": ["b"], "complete": True})
    assert response.json()["marked_removed"] == 0
    response = await api.post("/device/reconcile", json={"paths": [], "complete": True})
    assert response.json()["marked_removed"] == 1


async def test_rules_recognize_marathi():
    filters = await RulesQueryUnderstanding().extract("माझी गुणपत्रिका शोधा")
    assert filters.document_type == "marksheet"


async def test_production_never_trusts_loopback_or_disabled_pairing():
    from fastapi import HTTPException
    from starlette.datastructures import Headers

    from memora.api.routers.pairing import require_local_operator, require_paired_device
    from memora.config import Settings

    class Request:
        client = type("Client", (), {"host": "127.0.0.1"})()
        headers = Headers({})

    settings = Settings(
        environment="production", require_pairing=False, operator_secret="test-operator-secret"
    )
    with pytest.raises(HTTPException) as rejected:
        await require_paired_device(Request(), settings, PairingStore())
    assert rejected.value.status_code == 401
    with pytest.raises(HTTPException) as rejected:
        await require_local_operator(Request(), settings)
    assert rejected.value.status_code == 403


async def test_changed_path_replaces_old_document(api):
    first = await api.post(
        "/uploads", data={"device_path": "a"}, files={"file": ("123.txt", b"Old receipt")}
    )
    second = await api.post(
        "/uploads", data={"device_path": "a"}, files={"file": ("123.txt", b"New receipt")}
    )
    assert first.json()["memory_id"] != second.json()["memory_id"]
    results = (await api.post("/search", json={"query": "receipt", "images": False})).json()[
        "results"
    ]
    by_id = {r["memory_id"]: r for r in results}
    assert by_id[first.json()["memory_id"]]["removed_at"]
    assert not by_id[second.json()["memory_id"]]["removed_at"]


async def test_absence_cancels_pending_job_and_return_requeues(api):
    payload = {"device_path": "a"}
    file = {"file": ("123.txt", b"Aadhaar synthetic")}
    created = (await api.post("/index/jobs", data=payload, files=file)).json()
    await api.post("/device/reconcile", json={"paths": [], "complete": True})
    assert (await api.get("/index/jobs/" + created["id"])).json()["status"] == "superseded"
    returned = (await api.post("/index/jobs", data=payload, files=file)).json()
    assert returned["id"] == created["id"] and returned["status"] == "queued"


async def test_failed_job_manual_retry_and_isolation(api, db, test_user_id):
    from uuid import UUID

    created = (
        await api.post(
            "/index/jobs",
            data={"device_path": "a"},
            files={"file": ("123.txt", b"Aadhaar synthetic")},
        )
    ).json()
    job = await IndexJobRepository(db, test_user_id).get(UUID(created["id"]))
    job.status, job.error, job.attempts = "failed", "Interrupted", 5
    response = await api.post(f"/index/jobs/{job.id}/retry")
    assert response.json()["status"] == "queued" and response.json()["attempts"] == 0


async def test_month_query_disambiguates_receipts(api, app):
    from memora.api.routers.search import get_query_understanding

    app.dependency_overrides[get_query_understanding] = RulesQueryUnderstanding
    for name, date in [("1.txt", "01/02/2026"), ("2.txt", "04/03/2026")]:
        response = await api.post(
            "/uploads", files={"file": (name, f"Receipt\nDate: {date}\nAmount paid 400".encode())}
        )
        assert response.status_code == 201
    result = (
        await api.post("/search", json={"query": "receipt from March 2026", "images": False})
    ).json()
    assert result["results"][0]["filename"] == "2.txt"


def test_chunks_keep_page_and_bound_long_paragraphs():
    from memora.services.chunking import MAX_TOKENS, Block, chunk_blocks

    from support import FakeCounter

    chunks = chunk_blocks(
        [
            Block(text="Cover page", page=1),
            Block(text=" ".join(f"Aadhaar{i} synthetic{i}" for i in range(1000)), page=2),
        ],
        title="123",
        counter=FakeCounter(),
    )
    assert all(c.token_count <= MAX_TOKENS for c in chunks)
    assert all(c.page == 2 for c in chunks if "Aadhaar" in c.text)
    assert not chunks[-2].text.endswith(chunks[-1].text)


async def test_lexical_search_survives_embedding_outage(api, app):
    from memora.api.routers.search import get_embedder

    await api.post(
        "/uploads",
        files={"file": ("123.txt", b"Unique Identification Authority Aadhaar synthetic")},
    )
    app.dependency_overrides[get_embedder] = lambda: None
    response = await api.post("/search", json={"query": "mera adhaar", "images": False})
    assert response.status_code == 200
    assert response.json()["results"][0]["filename"] == "123.txt"
    assert response.json()["degraded_message"]


async def test_separate_folder_removals_do_not_keep_a_phantom_copy(api):
    data = make_pdf(["Aadhaar synthetic"])
    for path in ("folder-a/card.pdf", "folder-b/card.pdf"):
        await api.post("/uploads", data={"device_path": path}, files={"file": ("123.pdf", data)})
    first = await api.post(
        "/device/reconcile", json={"paths": [], "complete": True, "path_prefix": "folder-a/"}
    )
    assert first.json()["marked_removed"] == 0
    second = await api.post(
        "/device/reconcile", json={"paths": [], "complete": True, "path_prefix": "folder-b/"}
    )
    assert second.json()["marked_removed"] == 1


async def test_job_history_paginates_without_crossing_library(api):
    for path in ("a", "b"):
        await api.post(
            "/index/jobs",
            data={"device_path": path},
            files={"file": ("123.txt", b"Synthetic receipt")},
        )
    first = (await api.get("/index/jobs?limit=1&offset=0")).json()
    second = (await api.get("/index/jobs?limit=1&offset=1")).json()
    assert first["counts"]["queued"] == 2
    assert len(first["jobs"]) == len(second["jobs"]) == 1
    assert first["jobs"][0]["id"] != second["jobs"][0]["id"]
    assert (await api.get("/index/jobs?limit=0")).status_code == 422


def test_indic_words_keep_vowel_marks():
    from memora.services.lexical import bm25, tokens

    assert tokens("माझे गुणपत्रिका पावती") == ["गुणपत्रिका", "पावती"]
    assert tokens("मेरा आधार") == ["आधार"]
    assert bm25("दिन", ["दिन", "दान"])[1] == 0
    assert classify(text="आधारित योजना") is None
    assert classify(text="आधार कार्ड") == "aadhaar"


async def test_exact_match_opens_page_even_when_dense_prefers_cover(api, app):
    from memora.api.routers.search import get_embedder

    from support import FakeEmbedder

    cover = "General project overview background information"
    uploaded = await api.post(
        "/uploads", files={"file": (
            "928465.pdf", make_pdf([cover, "Unique reference ZXKRAIL on this page"]),
            "application/pdf",
        )},
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

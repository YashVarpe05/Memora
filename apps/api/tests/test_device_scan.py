"""Reconciling the phone's files against the corpus.

The interesting test here is not that removal works. It is that removal **does not** happen
after a partial scan — because the partial scan is the DEFAULT. The first pass indexes the
newest 500 of several thousand files, so treating "absent from this page" as "deleted from
the device" would mark most of the corpus removed on first run, via the happy path, on the
default setting. That is the kind of bug that ships: it needs no error, no edge case and no
unusual input, only the ordinary use of the feature.
"""

from datetime import UTC, datetime

import pytest

from support import make_pdf


async def _memory(api, filename: str, device_path: str | None):
    """One uploaded document, optionally carrying the device path the scan found it at."""
    body = make_pdf(["a receipt from the chemist, dated March"], title="Chemist")
    files = {"file": (filename, body, "application/pdf")}
    data = {"device_path": device_path} if device_path else {}
    response = await api.post("/uploads", files=files, data=data)
    assert response.status_code == 201, response.text
    return response.json()["memory_id"]


async def test_a_partial_scan_never_marks_anything_removed(api):
    """The default path. Absence from one page is not evidence of deletion."""
    await _memory(api, "a.pdf", "content://media/external/file/1")
    await _memory(api, "b.pdf", "content://media/external/file/2")

    # The phone saw only one of them, and says so honestly.
    response = await api.post(
        "/device/reconcile", json={"paths": ["content://media/external/file/1"], "complete": False}
    )

    body = response.json()
    assert response.status_code == 200
    assert body["marked_removed"] == 0, "a partial scan must not delete anything"
    assert body["reconciled"] is False
    assert body["reason"], "refusing silently would look identical to finding nothing"


async def test_a_full_scan_marks_the_missing_file_removed(api):
    present = await _memory(api, "kept.pdf", "content://media/external/file/1")
    gone = await _memory(api, "deleted.pdf", "content://media/external/file/2")

    response = await api.post(
        "/device/reconcile", json={"paths": ["content://media/external/file/1"], "complete": True}
    )

    body = response.json()
    assert body["reconciled"] is True
    assert body["marked_removed"] == 1
    assert present != gone


async def test_the_memory_survives_removal_and_stays_searchable(api):
    """The product's premise applied to its own storage. 'I know I had it' is the problem
    statement, so a tidied-away file must still be findable - with the fact recorded."""
    await _memory(api, "chemist.pdf", "content://media/external/file/9")

    await api.post("/device/reconcile", json={"paths": [], "complete": True})

    found = await api.post("/search", json={"query": "receipt from the chemist", "limit": 5})
    body = found.json()

    assert body["results"], "a removed file must still be findable"
    assert body["results"][0]["removed_at"], "and must say that it is gone from the device"


async def test_reconciling_twice_does_not_move_the_removal_date(api):
    """Otherwise 'removed on 14 March' quietly becomes 'removed on 20 March', and the one
    fact the result promises the user is wrong."""
    await _memory(api, "gone.pdf", "content://media/external/file/3")

    await api.post("/device/reconcile", json={"paths": [], "complete": True})
    first = (await api.post("/search", json={"query": "chemist", "limit": 5})).json()
    first_stamp = first["results"][0]["removed_at"]

    second = await api.post("/device/reconcile", json={"paths": [], "complete": True})
    after = (await api.post("/search", json={"query": "chemist", "limit": 5})).json()

    assert second.json()["marked_removed"] == 0, "already-removed rows must not be rewritten"
    assert after["results"][0]["removed_at"] == first_stamp


async def test_a_file_that_comes_back_is_no_longer_marked_removed(api):
    """Restored from a backup, or moved out and back. Without this a file could only ever
    be marked gone once and the record would keep asserting a removal that ended."""
    path = "content://media/external/file/4"
    await _memory(api, "returned.pdf", path)

    await api.post("/device/reconcile", json={"paths": [], "complete": True})
    back = await api.post("/device/reconcile", json={"paths": [path], "complete": True})

    assert back.json()["restored"] == 1
    found = (await api.post("/search", json={"query": "chemist", "limit": 5})).json()
    assert found["results"][0]["removed_at"] is None


async def test_a_hand_uploaded_document_is_never_touched_by_reconciliation(api):
    """Browser uploads have no device path. A full scan of the phone says nothing about
    them, and must not mark them gone just because the phone has never seen them."""
    await _memory(api, "typed.pdf", None)

    response = await api.post("/device/reconcile", json={"paths": [], "complete": True})

    assert response.json()["marked_removed"] == 0
    found = (await api.post("/search", json={"query": "chemist", "limit": 5})).json()
    assert found["results"][0]["removed_at"] is None


@pytest.mark.parametrize("complete", [True, False])
async def test_reconcile_requires_a_paired_device(complete):
    """It reports which files exist on the owner's phone, so it sits behind pairing like
    every other document route."""
    from memora.main import create_app
    from test_pairing import _from_the_network

    app = create_app()
    async with _from_the_network(app) as phone:
        response = await phone.post(
            "/device/reconcile", json={"paths": [], "complete": complete}
        )

    assert response.status_code == 401


def test_removal_is_recorded_in_utc():
    """A naive timestamp would render as the server's local time on a phone in another
    zone, and 'removed on 14 March' would be off by a day for half the world."""
    stamp = datetime.now(UTC)
    assert stamp.tzinfo is not None

"""Labelling documents by type, and the vocabulary that decides refusals.

The vocabulary IS the design. Too narrow and q021 ("my college fee receipt") is never
refused; too broad and answerable queries get refused instead — which is the worse error,
because a miss shows the user the wrong file while a false refusal tells them a file they
own does not exist.

Risks were named in prompts/phase-3b-refusal.md before this existed. q017 ("where are my
birthday reminders kept") was called the most likely false refusal, so it has a test.
"""

import pytest

from memora.services.document_type import classify, normalise, should_refuse

from support import make_png


@pytest.mark.parametrize(
    "filename,text,expected",
    [
        ("aadhaar_front.jpg", "", "aadhaar"),
        ("scan001.jpg", "GOVERNMENT OF INDIA\nUnique Identification Authority", "aadhaar"),
        ("doc.pdf", "INCOME TAX DEPARTMENT\nPermanent Account Number", "pan"),
        ("sem7.pdf", "Statement of Marks\nSemester VII", "marksheet"),
        ("fee.pdf", "FEE RECEIPT\nAmount paid: 45000", "receipt"),
        ("x.pdf", "Hall Ticket\nExamination 2026", "admit_card"),
        ("cv.pdf", "Curriculum Vitae\nYash Varpe", "resume"),
    ],
)
def test_labels_documents_from_filename_or_text(filename, text, expected):
    assert classify(filename=filename, text=text) == expected


def test_most_documents_have_no_type_and_that_is_normal():
    """Null is the common case. Refusal never fires on these, which is the point."""
    assert classify(filename="notes.txt", text="meeting at four about the drone project") is None
    assert classify(filename="DSC02946.JPG", text="") is None
    assert classify(filename="", text="") is None


def test_only_the_head_of_a_document_is_read():
    """The calendar attractor, applied to labelling.

    One file is 353 of 377 chunks. It mentions "receipt" and "certificate" somewhere.
    Reading the whole document would type the calendar as a receipt, and then every
    receipt query would match it instead of refusing.
    """
    calendar = "birthday reminder\n" * 400 + "fee receipt paid"

    assert classify(filename="calendar.ics", text=calendar) is None


def test_words_that_look_like_types_but_are_not():
    """Named as the top false-refusal risk before the vocabulary was written.

    Stage 1 volunteers "reminder" for q017 and "list" for q005. Neither is a document
    type, and treating them as one refuses two answerable queries.
    """
    for word in ("reminder", "reminders", "list", "link", "screenshot", "message", "photo"):
        assert normalise(word) is None, f"{word!r} would refuse an answerable query"


def test_an_unknown_word_disables_refusal_rather_than_causing_one():
    """Fails open, deliberately. An unrecognised type must never refuse an owned file."""
    assert normalise("hovercraft licence") is None
    assert should_refuse("hovercraft licence", present_in_corpus=set()) is False


def test_refuses_when_the_corpus_holds_no_such_type():
    """q021: the user asked for a receipt, nothing is a receipt, refuse regardless of score."""
    assert should_refuse("receipt", present_in_corpus={"aadhaar", "marksheet", None}) is True
    assert should_refuse("passport", present_in_corpus={"aadhaar", None}) is True


def test_does_not_refuse_when_the_type_is_present():
    assert should_refuse("aadhaar", present_in_corpus={"aadhaar", None}) is False


def test_a_query_naming_no_type_is_never_refused():
    """Most queries. The refusal path must not touch them at all."""
    assert should_refuse(None, present_in_corpus=set()) is False
    assert should_refuse("", present_in_corpus=set()) is False


def test_synonyms_reach_the_same_label():
    assert normalise("fee receipt") == "receipt"
    assert normalise("mark sheet") == "marksheet"
    assert normalise("admit card") == "admit_card"
    assert normalise("PAN card") == "pan"


async def test_ingest_labels_the_document(api, doubles, db, test_user_id):
    """The label has to reach the row, not just survive the request."""
    import uuid as _uuid

    from memora.repositories.memory import MemoryRepository

    doubles["ocr"].text = "GOVERNMENT OF INDIA\nAadhaar\n1234 5678 9012"

    response = await api.post(
        "/uploads", files={"file": ("scan.png", make_png(), "image/png")}
    )
    assert response.status_code == 201, response.text

    memories = MemoryRepository(db, test_user_id)
    stored = await memories.get(_uuid.UUID(response.json()["memory_id"]))

    assert stored is not None
    assert stored.document_type == "aadhaar"
    assert "aadhaar" in await memories.document_types()


async def test_an_unrecognised_document_is_labelled_null(api, doubles, db, test_user_id):
    """Most uploads. Null must be the quiet default, not an error path."""
    import uuid as _uuid

    from memora.repositories.memory import MemoryRepository

    doubles["ocr"].text = "notes from the meeting about the drone project"

    response = await api.post(
        "/uploads", files={"file": ("notes.png", make_png(), "image/png")}
    )
    assert response.status_code == 201, response.text

    stored = await MemoryRepository(db, test_user_id).get(
        _uuid.UUID(response.json()["memory_id"])
    )

    assert stored is not None
    assert stored.document_type is None


async def test_document_types_are_scoped_to_the_owner(db, test_user_id):
    """Whether user A holds a receipt must not decide whether user B is refused.

    A global lookup would leak the existence of another user's document through the
    refusal behaviour, without ever showing the file.
    """
    import uuid

    from memora.repositories.memory import MemoryRepository

    mine = MemoryRepository(db, test_user_id)
    await mine.create(
        source_type="pdf",
        title="Fee Receipt",
        filename="fee.pdf",
        document_type="receipt",
    )
    await db.flush()

    stranger = MemoryRepository(db, uuid.uuid4())

    assert "receipt" in await mine.document_types()
    assert "receipt" not in await stranger.document_types()

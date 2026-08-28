"""What kind of document this is, and whether the corpus holds one.

Refusal cannot be a similarity threshold. Measured in `docs/PHASE3.md`: q021 ("my college
fee receipt", absent from the corpus) scores 0.647, above nine documents that are the
correct answer to their query. Catching it with a threshold means refusing eight correct
answers. **Absence is not low similarity** - the calendar genuinely contains events about
college and fees, so the score is real.

Document-type agreement tests the thing the user actually asked for. The user asked for a
receipt; nothing in the corpus is a receipt; refuse regardless of score.

**Rule-based, not model-based, on purpose.** A classifier at ingest is a second extractor,
and `PHASE3.md` measured what a weak extractor does: a wrong filter demoted correct answers
below the no-filter baseline. Rules cost nothing, run offline, and fail in ways that can be
read off the source. If rules prove insufficient the fallback is a narrower vocabulary, not
a model.

**Deliberately narrow.** The vocabulary covers identity and record documents - the ones the
product is about. Every word added is a chance to refuse something answerable, and a false
refusal is worse than a miss: a miss shows the user the wrong file, a false refusal tells
them a file they own does not exist.
"""

from __future__ import annotations

import re

# type -> the words that identify it. Matched against filename and extracted text.
# Ordered most specific first; the first match wins, so "pan card" beats a stray "card".
VOCABULARY: dict[str, tuple[str, ...]] = {
    "aadhaar": ("aadhaar", "aadhar", "आधार", "uidai", "unique identification authority"),
    "pan": ("pan card", "permanent account number", "income tax department"),
    "passport": ("passport", "republic of india passport"),
    "marksheet": ("marksheet", "mark sheet", "statement of marks", "grade card", "transcript"),
    "receipt": ("receipt", "paid vide", "amount paid", "payment receipt", "fee receipt"),
    "admit_card": ("admit card", "hall ticket", "roll number slip"),
    "certificate": ("certificate", "is hereby certified", "certified that"),
    "id_card": ("identity card", "student id", "college id", "employee id"),
    "resume": ("resume", "curriculum vitae"),
    "invoice": ("invoice", "tax invoice", "bill to"),
    "ticket": ("boarding pass", "pnr", "e-ticket"),
}

# Words that look like a document type but are not one in this corpus. Stage 1 volunteers
# these readily, and each would refuse an answerable query - see the risk table in
# prompts/phase-3b-refusal.md, where q017 was named before any of this was built.
NOT_A_TYPE = frozenset({"reminder", "reminders", "list", "link", "screenshot", "message",
                        "email", "mail", "chat", "photo", "note", "document", "file"})  # fmt: skip


def _haystack(*parts: str | None) -> str:
    """Lowercased, with separators normalised to spaces.

    Filenames use underscores and hyphens where the vocabulary uses spaces, so
    "college_id.jpg" would not match the `id_card` synonym "college id" without this.
    Found by `memora.eval.impact`, which reported that the file about to be added to fill
    the `document_identity` gap would not classify as an identity document at all.
    """
    joined = " ".join(p.lower() for p in parts if p)
    return re.sub(r"[_\-.]+", " ", joined)


def classify(filename: str | None = None, text: str | None = None) -> str | None:
    """Label a document. None means "no recognised type", which is the common case.

    Only the head of the text is read. A fee receipt says so at the top; a calendar that
    mentions the word "receipt" in one event three hundred lines down is not a receipt,
    and reading the whole document would label it as one.
    """
    hay = _haystack(filename, (text or "")[:1500])
    if not hay:
        return None
    for label, words in VOCABULARY.items():
        if any(word in hay for word in words):
            return label
    return None


def normalise(requested: str | None) -> str | None:
    """Map what stage 1 asked for onto the vocabulary, or None if it is not a type.

    Anything unrecognised becomes None, which disables refusal for that query. Failing
    open is correct here: an unknown word must never refuse a document the user owns.
    """
    if not requested:
        return None
    word = re.sub(r"[^a-z ]", "", requested.strip().lower())
    if not word or word in NOT_A_TYPE:
        return None
    if word in VOCABULARY:
        return word
    collapsed = word.replace(" ", "_")
    if collapsed in VOCABULARY:
        return collapsed
    for label, words in VOCABULARY.items():
        if any(word in synonym or synonym in word for synonym in words):
            return label
    return None


def should_refuse(requested: str | None, present_in_corpus: set[str | None]) -> bool:
    """The user asked for a type the corpus does not contain.

    Both halves are required. No recognised request means no refusal, and that is the
    normal path for most queries.
    """
    wanted = normalise(requested)
    if wanted is None:
        return False
    return wanted not in present_in_corpus

"""Does this query carry anything stage 1 could turn into a filter?

Stage 1 costs one generate call, and the free tier allows twenty a day. When a query
contains no source-type word, no sender, and no date, stage 1 reliably returns an empty
extraction - it spends a call to say "no constraints", which is what the caller assumed
anyway. This check answers the same question locally, for free.

**It is a cost optimisation, not a quality one.** Skipping can only ever lose a filter,
never gain one. It is worth doing where the filter would have been empty, and harmful
everywhere else, so the vocabulary is kept deliberately narrow: when in doubt, run stage 1.

**What it structurally cannot see: entities.** `drone`, `uber`, `uipath`, `tcs`, `youtube`
look like ordinary lowercase words. Recognising them locally would need a gazetteer built
from the user's own corpus, which is a different feature with its own privacy questions.
Every known harm from this check is an entity it is blind to - see
`prompts/phase-3c-skip-stage1.md`, where those rows were named before this file existed.

Sender and date are matched as **patterns, not word lists**. A bare-word list containing
"to", "by", "last" or "this" matches almost every English sentence and would skip nothing,
while looking like it worked.
"""

from __future__ import annotations

import re

# Words that map to a source_type. Specific enough to match as bare words.
SOURCE_WORDS = frozenset(
    {
        "photo", "photos", "picture", "pictures", "pic", "pics",
        "image", "images", "screenshot", "screenshots", "scan", "scanned",
        "mail", "mails", "email", "emails", "inbox",
        "whatsapp", "chat", "chats", "message", "messages", "dm",
        "calendar", "event", "events", "reminder", "reminders",
        "meeting", "meetings", "invite", "schedule",
        "pdf", "pdfs", "document", "documents", "doc", "docs", "file", "files",
        "audio", "recording", "voice", "note", "notes",
    }
)  # fmt: skip

# Dates that stand alone. "last" and "this" are excluded on purpose - they carry a date
# only when paired with a period, which _RELATIVE_DATE handles.
TIME_WORDS = frozenset(
    {
        "when", "today", "yesterday", "tomorrow", "tonight",
        "recent", "recently", "lately", "ago",
        "january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sept", "oct", "nov", "dec",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    }
)  # fmt: skip

def _document_type_words() -> frozenset[str]:
    """Single-word names for a KIND of document.

    Added 2026-08-27, with refusal. The vocabulary above was written when stage 1 returned
    only source types, senders and dates, so "my passport" carried no signal and was
    correctly skipped. Then refusal made `document_type` a filter - and the skip silently
    disabled refusal for exactly the queries it exists for. q020 "my passport" and q021
    "my college fee receipt" never reached stage 1, so there was no type to disagree with,
    and refusal accuracy stayed at 0.000 while the extractor was working perfectly.

    Derived from `document_type.VOCABULARY` so there is ONE source of truth: adding a
    document type there cannot leave this list behind.
    """
    from memora.services.document_type import VOCABULARY

    words: set[str] = set()
    for label, synonyms in VOCABULARY.items():
        words.add(label.replace("_", " "))
        words.update(synonyms)
    # Single tokens only. Multi-word synonyms are matched as phrases in reasons().
    return frozenset(w for w in words if " " not in w and w.isascii())


DOCUMENT_WORDS = _document_type_words()

_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_RELATIVE_DATE = re.compile(
    r"\b(?:last|this|next|past|previous)\s+"
    r"(?:year|month|week|day|night|weekend|semester|summer|winter|monsoon)\b"
)
_SENDER = re.compile(
    r"\bfrom\s+\w+"  # from aradhana
    r"|\b\w+\s+sent\b"  # anu priya sent
    r"|\bsent\s+(?:to|by|me)\b"  # sent to rutuja
    r"|\bforwarded\b|\bshared\s+by\b|\breplied\b|\bwrote\s+to\b"
)
_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(query: str) -> set[str]:
    return set(_TOKEN.findall(query.lower()))


def has_filterable_signal(query: str) -> bool:
    """True when stage 1 is worth a call.

    Errs toward True. A wrong False loses a filter the query needed; a wrong True costs
    one call out of twenty. Those are not symmetric, and the asymmetry sets the default.
    """
    return bool(reasons(query))


def reasons(query: str) -> list[str]:
    """What was matched, so a skip can be inspected rather than trusted."""
    lowered = query.lower()
    words = _tokens(query)
    found = sorted(words & SOURCE_WORDS) + sorted(words & TIME_WORDS)
    found += sorted(words & DOCUMENT_WORDS)
    # Multi-word types: "pan card", "admit card", "mark sheet".
    from memora.services.document_type import VOCABULARY

    for synonyms in VOCABULARY.values():
        found += [p for p in synonyms if " " in p and p in lowered]
    if _YEAR.search(lowered):
        found.append("year")
    if match := _RELATIVE_DATE.search(lowered):
        found.append(match.group(0))
    if match := _SENDER.search(lowered):
        found.append(match.group(0))
    return found


def why(query: str) -> str:
    found = reasons(query)
    return "matched " + ", ".join(found) if found else "no source-type, sender or date word"

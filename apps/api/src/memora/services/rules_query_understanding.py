"""Stage 1 with no model in it.

**This exists to answer a question about the on-device build, not to save a few seconds.**
Every other component of the pipeline ports to a phone — ML Kit for OCR, ONNX for CLIP,
SQLite for storage. Stage 1 is the only piece that needs a 3B language model, so if rules
can do the extraction the phone build ships without an LLM at all: no 2 GB download, no
inference battery cost, no minimum-RAM floor. `prompts/rules-stage1.md` holds the
pre-registered predictions this is measured against.

Half of it was already rules-only before this file existed. `document_type` is read from
the query by `document_type.classify()` — the *same vocabulary that types the documents* —
which is what moved q024 to rank 1 after the local model turned out to return `None` for
that field on every query. This module extends that approach to the remaining fields.

Deterministic on purpose, and that is a property worth more than the latency: a table
cannot fail a quota, cannot time out, cannot be rate-limited, and cannot silently change
behaviour when a model is swapped. Every failure mode `stage1_health.py` exists to watch
for is absent by construction.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from memora.services.document_type import classify
from memora.services.query_signal import _SENDER, _TOKEN, SOURCE_WORDS
from memora.services.query_understanding import QueryFilters

# A query word maps to the `source_type` the ingest pipeline actually stores. The words
# themselves are reused from query_signal so the skip heuristic and the extractor cannot
# disagree about what counts as a signal.
SOURCE_MAP: dict[str, str] = {
    "photo": "image", "photos": "image", "picture": "image", "pictures": "image",
    "pic": "image", "pics": "image", "image": "image", "images": "image",
    "screenshot": "image", "screenshots": "image", "scan": "image", "scanned": "image",
    "mail": "email", "mails": "email", "email": "email", "emails": "email",
    "inbox": "email",
    "whatsapp": "chat", "chat": "chat", "chats": "chat", "message": "chat",
    "messages": "chat", "dm": "chat",
    "calendar": "calendar", "event": "calendar", "events": "calendar",
    "reminder": "calendar", "reminders": "calendar", "meeting": "calendar",
    "meetings": "calendar", "invite": "calendar", "schedule": "calendar",
    "pdf": "pdf", "pdfs": "pdf",
}  # fmt: skip

# Deliberately NOT mapped: "document", "documents", "doc", "docs", "file", "files",
# "note", "notes". They name a thing rather than a medium, and every stored document is a
# file - a filter that matches everything is a filter that costs a query its bonus.
assert not (set(SOURCE_MAP) - SOURCE_WORDS), "SOURCE_MAP must draw only on SOURCE_WORDS"

# "last year", "this month". Resolved to a concrete range here rather than deferred, which
# is strictly more than the model does with the same phrase.
_RELATIVE = re.compile(
    r"\b(last|this|past|previous)\s+(year|month|week)\b", re.IGNORECASE
)

# Words that sit inside a sender phrase without being a person.
#
# The verbs matter as much as the pronouns. `_SENDER` matches "forwarded" and
# "shared by" on their own, so "someone forwarded to me on whatsapp" yielded
# `sender="forwarded"` - a filter looking for a person called Forwarded, which
# matches nothing and costs the query its bonus. Caught by reading the extraction
# before measuring rather than by the number being slightly worse.
_NOT_A_NAME = frozenset(
    {"me", "my", "the", "a", "an", "someone", "somebody", "him", "her", "them", "it",
     "email", "whatsapp", "gmail", "phone", "college", "work", "home", "there", "here",
     "forwarded", "shared", "replied", "wrote", "sent"}
)  # fmt: skip


def _source_types(query: str) -> tuple[str, ...]:
    """Media the query names.

    Order-preserving and de-duplicated so the filter is stable across runs; a set would
    make the extracted filters differ between processes and the eval unreproducible.
    """
    seen: list[str] = []
    for token in _TOKEN.findall(query.lower()):
        mapped = SOURCE_MAP.get(token)
        if mapped and mapped not in seen:
            seen.append(mapped)
    return tuple(seen)


def _sender(query: str) -> str | None:
    """A person named as the source, if the sentence names one.

    Reuses `query_signal._SENDER` to decide THAT a sender is present, then takes the name
    out of the match. Two tables would drift; one table cannot.
    """
    match = _SENDER.search(query.lower())
    if match is None:
        return None

    phrase = match.group(0)
    words = [w for w in _TOKEN.findall(phrase) if w not in {"from", "sent", "to", "by"}]
    names = [w for w in words if w not in _NOT_A_NAME]
    if not names:
        return None

    # "anu priya sent" — the regex only captures one word before "sent", so the first name
    # is lost. Substring matching on either side still hits, which is why this is degraded
    # rather than broken. Recorded rather than papered over.
    return names[-1]


def _window(query: str, now: datetime) -> tuple[datetime | None, datetime | None, str | None]:
    """A concrete date range from a relative phrase, plus what was left unresolved."""
    match = _RELATIVE.search(query)
    if match is None:
        return None, None, None

    qualifier, period = match.group(1).lower(), match.group(2).lower()
    phrase = f"{qualifier} {period}"

    if period == "year":
        year = now.year - 1 if qualifier in {"last", "past", "previous"} else now.year
        return (
            datetime(year, 1, 1, tzinfo=UTC),
            datetime(year, 12, 31, 23, 59, 59, tzinfo=UTC),
            phrase,
        )

    # Months and weeks resolve to a span rather than a calendar boundary. Approximate on
    # purpose: the filter is a boost, not a WHERE clause, and a document just outside a
    # month boundary should not be excluded by arithmetic.
    days = 31 if period == "month" else 7
    span = days * (1 if qualifier in {"this"} else 2)
    from datetime import timedelta

    return now - timedelta(days=span), now, phrase


class RulesQueryUnderstanding:
    """Stage 1 as a lookup. Satisfies the same Protocol the model implementations do."""

    name = "rules"

    async def extract(self, query: str, *, today: datetime | None = None) -> QueryFilters:
        now = today or datetime.now(UTC)
        after, before, unresolved = _window(query, now)

        return QueryFilters(
            # The whole query. There is no model to rewrite it, and the embedding is
            # computed from this - truncating it would change the dense arm, which would
            # make this a different experiment rather than a different stage 1.
            semantic_query=query,
            source_types=_source_types(query),
            sender=_sender(query),
            document_type=classify(text=query),
            after=after,
            before=before,
            needs_time_resolution=unresolved,
            # Never fails. No quota, no transport, no parse - so `failed` is False by
            # construction, and a health check that ever reports otherwise is watching
            # the wrong arm.
            failed=False,
            raw={"provider": "rules"},
        )

"""Stage 1 — the question becomes filters.

PRODUCT.md architectural rule 1 permits exactly one kind of model call at layer one: one
whose entire input is the user's own query text. This module is that call. It reads the
question and returns constraints. It never sees a document, a chunk, a filename or a
result, and `extract()` takes a `str` so there is nothing else it could see.

The filters are applied as **boosts, not exclusions** — see `services/search.py`. That is
not timidity. `mail.pdf` in the real corpus is a scanned print of a Gmail message, so its
`source_type` is `pdf` while the query calls it "the mail". A strict `source_type: email`
filter would exclude the correct answer and score worse than no filtering at all. In a
personal corpus the format a thing arrives in rarely matches what it is.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from memora.config import get_settings
from memora.services.masking import mask_identifiers

# The source types the corpus actually contains. Given to the model so it chooses from
# what exists rather than inventing a taxonomy - and so it can be told that a scanned
# email is a `pdf`.
SOURCE_TYPES = ("pdf", "image", "calendar", "email", "chat")

SYSTEM_PROMPT = """You turn a person's description of a document they are looking for
into search constraints. You never see the documents themselves.

Return ONLY a JSON object, no prose and no markdown fence, with these keys:

  source_types      array from: pdf, image, calendar, email, chat. [] if unclear.
  sender            a person's name if the query names who sent or wrote it, else null.
  entities          array of people, organisations or products named in the query.
  after             ISO date (YYYY-MM-DD) or null - earliest the document could be.
  before            ISO date (YYYY-MM-DD) or null - latest the document could be.
  semantic_query    the part of the question that needs meaning-based search, with
                    filler like "the", "that thing", "i saved somewhere" removed.
  needs_time_resolution  the vague time phrase if there is one ("last semester"), else null.

Guidance that matters:
- A screenshot, photo or "picture of" is `image`. A message thread is `chat`.
- **A scanned or printed email saved as a file is `pdf`, not `email`.** When a query says
  "mail" or "email", include BOTH `email` and `pdf`, because personal archives are full
  of emails saved as PDFs.
- Relative dates resolve against the current date given below.
- If you are unsure, return fewer constraints. An empty array is better than a wrong one.
"""


@dataclass(frozen=True)
class QueryFilters:
    """What stage 1 extracted. Every field is optional and advisory."""

    semantic_query: str
    source_types: tuple[str, ...] = ()
    sender: str | None = None
    entities: tuple[str, ...] = ()
    after: datetime | None = None
    before: datetime | None = None
    needs_time_resolution: str | None = None
    failed: bool = False
    failure_reason: str | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def is_empty(self) -> bool:
        return not (self.source_types or self.sender or self.after or self.before)


def passthrough(query: str, reason: str = "not run") -> QueryFilters:
    """No constraints. The fallback whenever stage 1 cannot be trusted."""
    return QueryFilters(semantic_query=query, failed=True, failure_reason=reason)


class QueryUnderstanding(Protocol):
    async def extract(self, query: str) -> QueryFilters: ...


def _parse_date(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip()).replace(tzinfo=UTC)
    except ValueError:
        return None


def _strings(value: object, allowed: tuple[str, ...] | None = None) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out = [str(v).strip().lower() for v in value if str(v).strip()]
    if allowed is not None:
        out = [v for v in out if v in allowed]
    return tuple(dict.fromkeys(out))


def parse_response(text: str, query: str) -> QueryFilters:
    """Turn the model's reply into filters, or fall back to no constraints.

    A malformed or hostile reply degrades to unfiltered dense search. A search that
    degrades beats a search that 500s, and the caller cannot tell the difference except
    in the reported filters.
    """
    body = text.strip()
    if body.startswith("```"):
        body = body.strip("`")
        body = body[body.index("{") :] if "{" in body else body

    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return passthrough(query, reason="unparseable JSON")
    if not isinstance(data, dict):
        return passthrough(query, reason="reply was not an object")

    semantic = data.get("semantic_query")
    sender = data.get("sender")

    return QueryFilters(
        semantic_query=str(semantic).strip() if semantic else query,
        source_types=_strings(data.get("source_types"), SOURCE_TYPES),
        sender=str(sender).strip() if isinstance(sender, str) and sender.strip() else None,
        entities=_strings(data.get("entities")),
        after=_parse_date(data.get("after")),
        before=_parse_date(data.get("before")),
        needs_time_resolution=(
            str(data["needs_time_resolution"]).strip()
            if isinstance(data.get("needs_time_resolution"), str)
            and data["needs_time_resolution"].strip()
            else None
        ),
        raw=data,
    )


def build_prompt(query: str, today: datetime | None = None) -> str:
    """The entire model input. Takes a query string and nothing else, on purpose.

    The signature is the enforcement: there is no parameter through which a chunk, a
    filename or a result could arrive. See PRODUCT.md architectural rule 1.
    """
    when = (today or datetime.now(UTC)).date().isoformat()
    return f"Today is {when}.\n\nQuery: {mask_identifiers(query).value}"


class GeminiQueryUnderstanding:
    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model
        self._client = None

    async def extract(self, query: str) -> QueryFilters:
        from google import genai
        from google.genai import types

        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=build_prompt(query),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
        except Exception as exc:  # noqa: BLE001 - stage 1 must never fail a search
            # Degrading is right; degrading SILENTLY is not. A quota exhaustion made
            # every call fall back, and the run reported dense-only numbers as a stage 1
            # measurement - indistinguishable from stage 1 simply having no opinion.
            # The reason travels with the result so a caller can tell the difference.
            return passthrough(query, reason=f"{type(exc).__name__}: {exc}"[:200])

        return parse_response(response.text or "", query)


def build_query_understanding() -> QueryUnderstanding:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set. Query understanding is unavailable.")
    return GeminiQueryUnderstanding(
        api_key=settings.gemini_api_key, model=settings.gemini_model
    )

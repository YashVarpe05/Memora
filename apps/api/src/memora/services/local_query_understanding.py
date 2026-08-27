"""Stage 1 on a model that runs on this machine.

Free-only is a project constraint, and this is the only extractor configuration with no
daily cap, no deprecation risk, and no query leaving the device. `MODEL-RISK.md` records
the second reason it matters: `gemini-2.5-flash` is already closed to new users, so every
hosted stage 1 number in this project is unreproducible for anyone without a pre-cutoff
key. Local weights cannot be withdrawn.

**It has to earn its place.** `PHASE3.md` measured `gemini-flash-lite-latest` at Recall@1
0.789 - below the 0.842 achieved by using no extractor at all, because a wrong filter
actively demotes the right answer. The bar here is 0.842, not 0.947, and a result below it
is a finding to report rather than a prompt to iterate on. Predictions are in
`prompts/local-stage1.md`, written before this file existed.

**Constrained decoding is the reason this might work where flash-lite did not.** Stage 1
is structured extraction, not reasoning: fill a fixed schema from one short sentence.
Passing a JSON schema as `format` makes the decoder unable to emit anything invalid, which
removes an entire failure class the hosted path handles with a passthrough fallback. It
cannot fix a wrong guess about *which* source type - only a malformed one.

The SYSTEM_PROMPT is reused unchanged. Rewriting it for a smaller model would make the
arms measure two things at once, and the point is to isolate the extractor.
"""

from __future__ import annotations

import time

import httpx

from memora.services.document_type import VOCABULARY
from memora.services.query_understanding import (
    SOURCE_TYPES,
    SYSTEM_PROMPT,
    QueryFilters,
    build_prompt,
    parse_response,
    passthrough,
)

# The schema the decoder is constrained to. Mirrors what SYSTEM_PROMPT asks for; the
# prompt still explains the SEMANTICS, which a schema cannot.
STAGE1_SCHEMA = {
    "type": "object",
    "properties": {
        "source_types": {
            "type": "array",
            "items": {"type": "string", "enum": list(SOURCE_TYPES)},
        },
        "sender": {"type": ["string", "null"]},
        "entities": {"type": "array", "items": {"type": "string"}},
        "after": {"type": ["string", "null"]},
        "before": {"type": ["string", "null"]},
        "semantic_query": {"type": "string"},
        "needs_time_resolution": {"type": ["string", "null"]},
        # Enumerated, so the decoder cannot invent a type. An invented one would
        # refuse a document the person owns - the worst error this design can make.
        "document_type": {
            "type": ["string", "null"],
            "enum": [*VOCABULARY, None],
        },
    },
    "required": ["source_types", "semantic_query"],
}


class LocalQueryUnderstanding:
    """Same protocol as the hosted extractor, so every arm shares one call site."""

    def __init__(self, base_url: str, model: str, timeout: float = 180.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        # Generous: a 3B model on CPU is expected at 5-20s per query, and a timeout that
        # fires would be recorded as an extraction failure and quietly bias the arm.
        self._timeout = timeout
        self.last_ms: int | None = None

    @property
    def model(self) -> str:
        return self._model

    async def extract(self, query: str) -> QueryFilters:
        payload = {
            "model": self._model,
            "prompt": build_prompt(query),
            "system": SYSTEM_PROMPT,
            "stream": False,
            "format": STAGE1_SCHEMA,
            "options": {
                # Deterministic. A sampled extractor makes every measurement
                # unreproducible, which is half the reason this arm exists.
                "temperature": 0.0,
                "seed": 7,
                "num_predict": 256,
            },
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(f"{self._base_url}/api/generate", json=payload)
        except httpx.HTTPError as exc:
            self.last_ms = int((time.perf_counter() - started) * 1000)
            return passthrough(query, reason=f"{type(exc).__name__}: {exc}"[:200])
        finally:
            self.last_ms = int((time.perf_counter() - started) * 1000)

        if response.status_code != 200:
            return passthrough(
                query, reason=f"ollama {response.status_code}: {response.text[:120]}"
            )

        # parse_response is shared with the hosted path on purpose: identical parsing
        # means a difference between arms is the MODEL, not two parsers disagreeing.
        return parse_response(response.json().get("response", ""), query)


def build_local_query_understanding(model: str, base_url: str | None = None):
    from memora.config import get_settings

    return LocalQueryUnderstanding(base_url or get_settings().ollama_url, model)

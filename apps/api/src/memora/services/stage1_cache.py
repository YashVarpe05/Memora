"""A persistent cache for stage 1 extractions.

Measured 2026-08-24: the free tier allows **20 generateContent requests per day, per
model**. Stage 1 is one call per query and the gold set is 21 queries, so a single cold
evaluation exceeds the daily budget for one model. Not "two runs a day" - fewer than one.

The gold set runs the same 21 strings every time, so caching makes repeat runs free.

**The key includes the prompt, not just the query.** Keying on query text alone would
serve stale extractions after a prompt change, and the run would look fine while
measuring the previous prompt. That is the same failure this project keeps finding: a
check that verifies the wrong property. Change the system prompt and every entry
invalidates, which is correct and costs a cold run.

The cache is for evaluation. Real use pays the latency and the quota, and that trade-off
belongs in the report rather than hidden behind a cache that only the harness sees.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from memora.paths import anchored
from memora.services.query_understanding import (
    SYSTEM_PROMPT,
    QueryFilters,
    QueryUnderstanding,
)

CACHE_PATH = "data/eval-runs/stage1-cache.json"


def cache_key(query: str, model: str, prompt: str = SYSTEM_PROMPT) -> str:
    digest = hashlib.sha256()
    digest.update(model.encode())
    digest.update(b"\x00")
    digest.update(prompt.encode())
    digest.update(b"\x00")
    digest.update(query.strip().lower().encode())
    return digest.hexdigest()


def _to_json(filters: QueryFilters) -> dict:
    data = asdict(filters)
    for field in ("after", "before"):
        value = data.get(field)
        data[field] = value.isoformat() if isinstance(value, datetime) else None
    data["source_types"] = list(filters.source_types)
    data["entities"] = list(filters.entities)
    return data


def _from_json(data: dict) -> QueryFilters:
    def when(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value).replace(tzinfo=UTC)
        except ValueError:
            return None

    return QueryFilters(
        semantic_query=data.get("semantic_query", ""),
        source_types=tuple(data.get("source_types") or ()),
        sender=data.get("sender"),
        entities=tuple(data.get("entities") or ()),
        after=when(data.get("after")),
        before=when(data.get("before")),
        needs_time_resolution=data.get("needs_time_resolution"),
        failed=bool(data.get("failed")),
        failure_reason=data.get("failure_reason"),
        raw=data.get("raw") or {},
    )


class CachingQueryUnderstanding:
    """Wraps a real extractor. Never caches a failure."""

    def __init__(
        self,
        inner: QueryUnderstanding,
        model: str,
        path: Path | None = None,
    ) -> None:
        self._inner = inner
        self._model = model
        self._path = Path(path) if path else anchored(CACHE_PATH)
        self._entries: dict[str, dict] = {}
        self.hits = 0
        self.misses = 0
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._entries = json.loads(self._path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                self._entries = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._entries, indent=2, sort_keys=True), encoding="utf-8", newline="\n"
        )

    async def extract(self, query: str) -> QueryFilters:
        key = cache_key(query, self._model)
        cached = self._entries.get(key)
        if cached is not None:
            self.hits += 1
            return _from_json(cached)

        self.misses += 1
        filters = await self._inner.extract(query)

        # A failure is not an answer. Caching one would freeze a quota outage into the
        # cache and every later run would replay it as though stage 1 had no opinion.
        if not filters.failed:
            self._entries[key] = _to_json(filters)
            self._save()

        return filters

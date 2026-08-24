"""Whether stage 1 is actually working, observed rather than probed.

The worst failure this system can have is silent degradation. Stage 1 falls back to
passthrough on any error, which is correct - a search that degrades beats a search that
500s. But when the daily quota runs out mid-demo, every subsequent search quietly reverts
to dense-only retrieval: the calendar starts winning queries it should not, Recall@1 drops
from 0.947 to 0.842, and nothing on screen says why. That already happened once during
measurement and was nearly written up as a result.

Observed, not probed, on purpose. Asking the API whether quota remains costs a call
against the very quota being checked - twenty per day, so a health check every thirty
seconds would exhaust it before anyone searched. This records what actually happened to
real searches instead, which costs nothing and is the thing worth knowing.

Process-local and deliberately so. It answers "is this instance degrading right now",
which is what a demo needs, not a durable metric.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime

WINDOW = 20


@dataclass(frozen=True)
class Stage1Status:
    state: str
    recent_calls: int
    recent_failures: int
    last_failure: str | None
    last_failure_at: str | None

    @property
    def degraded(self) -> bool:
        return self.state != "ok"


class Stage1Health:
    """A rolling window of recent stage 1 outcomes."""

    def __init__(self, window: int = WINDOW) -> None:
        self._outcomes: deque[bool] = deque(maxlen=window)
        self._last_failure: str | None = None
        self._last_failure_at: str | None = None

    def record(self, *, failed: bool, reason: str | None = None) -> None:
        self._outcomes.append(not failed)
        if failed:
            self._last_failure = reason or "unknown"
            self._last_failure_at = datetime.now(UTC).isoformat(timespec="seconds")

    def status(self) -> Stage1Status:
        total = len(self._outcomes)
        failures = sum(1 for ok in self._outcomes if not ok)

        if total == 0:
            state = "unknown"
        elif failures == 0:
            state = "ok"
        elif failures == total:
            # Every recent search silently ran dense-only. This is the demo-day case.
            state = "down"
        else:
            state = "degraded"

        return Stage1Status(
            state=state,
            recent_calls=total,
            recent_failures=failures,
            last_failure=self._last_failure,
            last_failure_at=self._last_failure_at,
        )


_health = Stage1Health()


def health() -> Stage1Health:
    return _health


def describe(status: Stage1Status) -> str | None:
    """A sentence a person can act on, or None when nothing is wrong."""
    if status.state == "ok" or status.state == "unknown":
        return None
    if status.state == "down":
        return (
            "Query understanding is unavailable, so searches are running on plain "
            "similarity only and results will be worse. Most likely the daily API quota "
            f"is exhausted. Last error: {status.last_failure}"
        )
    return (
        f"Query understanding failed on {status.recent_failures} of the last "
        f"{status.recent_calls} searches. Results may be worse than usual. "
        f"Last error: {status.last_failure}"
    )

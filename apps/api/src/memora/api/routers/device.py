"""Reconciling what the phone still holds against what the corpus remembers.

The scan uploads what it finds. This answers the other half — what it *stopped* finding —
so a file deleted from the phone becomes "removed from device on 14 March" rather than a
result that fails to open.

**The dangerous case is a partial scan, and it is the default one.** The first pass indexes
the newest 500 of several thousand files. If absence from that page were read as deletion,
the very first scan would mark most of the corpus removed — a data-destroying bug reached
by the happy path, on the default setting, with every test passing. So removal is computed
only from a scan that says it enumerated everything, and `complete=false` is accepted and
explicitly does nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from memora.api.deps import CurrentUserDep, DbDep
from memora.repositories.memory import MemoryRepository

router = APIRouter(tags=["device"])


class ReconcileRequest(BaseModel):
    """Device paths the scan saw this run."""

    paths: list[str] = Field(default_factory=list)
    # Whether the scan enumerated the whole device. Only a complete scan can prove absence.
    complete: bool = False
    path_prefix: str | None = Field(default=None, max_length=1024)


class ReconcileResponse(BaseModel):
    seen: int
    marked_removed: int
    restored: int
    # Echoed back so a caller cannot mistake "did nothing, by design" for "found nothing".
    reconciled: bool
    reason: str | None = None


@router.post("/device/reconcile", response_model=ReconcileResponse)
async def reconcile_device(
    payload: ReconcileRequest,
    session: DbDep,
    user_id: CurrentUserDep,
) -> ReconcileResponse:
    memories = MemoryRepository(session, user_id)

    if not payload.complete:
        # Not an error. A quick scan is the default and is expected to land here.
        return ReconcileResponse(
            seen=len(payload.paths),
            marked_removed=0,
            restored=0,
            reconciled=False,
            reason=(
                "A partial scan cannot prove a file is gone - it only proves it was not "
                "in this page. Run a full scan to reconcile removals."
            ),
        )

    from memora.repositories.index_job import IndexJobRepository

    await IndexJobRepository(session, user_id).reconcile(set(payload.paths), payload.path_prefix)
    known = await memories.device_paths()
    if payload.path_prefix:
        known = {p: mid for p, mid in known.items() if p.startswith(payload.path_prefix)}
    seen = set(payload.paths)

    returned = list({memory_id for path, memory_id in known.items() if path in seen})
    # Another copy, including one outside a browser folder scan, keeps a document present.
    all_paths = await memories.device_paths()
    outside = {mid for p, mid in all_paths.items() if p not in known}
    missing = list(set(known.values()) - set(returned) - outside)

    marked = await memories.mark_removed(missing, datetime.now(UTC))
    # A file can come back - restored from a backup, or moved out and back again.
    restored = await memories.mark_present(returned)
    await memories.forget_missing_locations(set(known) - seen)

    return ReconcileResponse(
        seen=len(seen),
        marked_removed=marked,
        restored=restored,
        reconciled=True,
    )

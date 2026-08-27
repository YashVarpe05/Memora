"""CLI for the backfill. See services/backfill.py for why it is general.

    uv run python -m memora.backfill --user <uuid>
    uv run python -m memora.backfill --user <uuid> --apply
"""

from __future__ import annotations

import argparse
import asyncio
import uuid


async def main_async(user_id: uuid.UUID, apply: bool) -> int:
    from memora.db.session import scoped_session
    from memora.services.backfill import ImageEmbeddingBackfiller, run_backfill
    from memora.services.image_embedding import build_image_embedder
    from memora.services.storage import build_blob_store

    backfillers = [ImageEmbeddingBackfiller(build_image_embedder(), build_blob_store())]

    async for session in scoped_session(user_id):
        missing, produced = await run_backfill(session, user_id, backfillers, apply)

        if not missing:
            print("  nothing missing - every document has its derived artifacts")
            return 0

        print(f"  {len(missing)} missing artifact(s):")
        for item in missing:
            print(f"    {item.artifact:<18} {item.filename[:52]}")

        if not apply:
            print()
            print("  reported only. Re-run with --apply to produce them.")
            return 0

        await session.commit()
        print()
        print(f"  produced {len(produced)} of {len(missing)}")
        skipped = [m for m in missing if m not in produced]
        for item in skipped:
            print(f"    SKIPPED {item.artifact} for {item.filename[:44]} (blob missing?)")
        return 0 if len(produced) == len(missing) else 1
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", required=True, help="owner UUID")
    parser.add_argument(
        "--apply", action="store_true", help="write the artifacts; otherwise report only"
    )
    args = parser.parse_args(argv)
    return asyncio.run(main_async(uuid.UUID(args.user), args.apply))


if __name__ == "__main__":
    raise SystemExit(main())

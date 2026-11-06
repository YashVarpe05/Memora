"""Populate missing/current-model text vectors without re-uploading documents.

python -m memora.text_backfill --all-devices --watch
python -m memora.text_backfill --device-id <uuid> --status
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from uuid import UUID

from memora.config import get_settings
from memora.db.session import dispose_engine, scoped_session
from memora.repositories.chunk import ChunkRepository
from memora.services.embedding import build_embedder, embedding_fingerprint
from memora.services.embedding_backfill import backfill_batch
from memora.services.pairing import store


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    devices = result.add_mutually_exclusive_group(required=True)
    devices.add_argument("--all-devices", action="store_true")
    devices.add_argument("--device-id", type=UUID)
    result.add_argument(
        "--watch", action="store_true", help="Discover newly indexed text continuously"
    )
    result.add_argument(
        "--status", action="store_true", help="Report pending chunks without embedding"
    )
    result.add_argument("--batch-size", type=int, default=16)
    result.add_argument(
        "--max-batches", type=int, default=0, help="Per-device pass limit; 0 means all"
    )
    result.add_argument("--poll-seconds", type=float, default=5)
    return result


async def run(args: argparse.Namespace) -> None:
    embedder = build_embedder()
    model_id = embedding_fingerprint(embedder)
    if not model_id:
        raise ValueError("Configured provider has no embedding model fingerprint")
    try:
        while True:
            identities = [args.device_id] if args.device_id else store().identities()
            if args.all_devices and not get_settings().is_production:
                identities.append(get_settings().dev_user_id)
            for identity in dict.fromkeys(identities):
                completed = 0
                failed = False
                if not args.status:
                    batches = 0
                    while not args.max_batches or batches < args.max_batches:
                        try:
                            async for session in scoped_session(identity):
                                async with asyncio.timeout(600):
                                    count = await backfill_batch(
                                        session, identity, embedder, batch_size=args.batch_size
                                    )
                            completed += count
                            if not count:
                                break
                            batches += 1
                        except Exception:
                            # Provider exception strings can contain request data or credentials.
                            # The next pass retries unchanged rows; already committed batches stay.
                            failed = True
                            break
                async for session in scoped_session(identity):
                    remaining = await ChunkRepository(session, identity).pending_embedding_count(
                        model_id
                    )
                print(
                    json.dumps(
                        {
                            "device_id": str(identity),
                            "model": model_id,
                            "completed_chunks": completed,
                            "pending_chunks": remaining,
                            "retry_needed": failed,
                        }
                    ),
                    flush=True,
                )
                if failed and not args.watch:
                    raise RuntimeError("Embedding batch interrupted; rerun to resume")
            if not args.watch:
                break
            await asyncio.sleep(args.poll_seconds)
    finally:
        await dispose_engine()


def main() -> None:
    command = parser()
    args = command.parse_args()
    if args.status and args.watch:
        command.error("--status and --watch cannot be combined")
    if not 1 <= args.batch_size <= 128 or args.max_batches < 0 or args.poll_seconds < 1:
        command.error("batch-size must be 1..128, max-batches >= 0, poll-seconds >= 1")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
    except Exception:
        print(
            "Text backfill interrupted. Check service configuration and rerun to resume.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

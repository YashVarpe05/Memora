"""Device-scoped durable job operations."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert

from memora.db.models.index_job import IndexJob
from memora.repositories.base import BaseRepository


class IndexJobRepository(BaseRepository[IndexJob]):
    model = IndexJob

    async def enqueue(self, content_hash: str, filename: str, device_path: str) -> IndexJob:
        await self.session.execute(
            update(IndexJob)
            .where(
                IndexJob.user_id == self.user_id,
                IndexJob.device_path == device_path,
                IndexJob.content_hash != content_hash,
                IndexJob.status.in_(["queued", "processing", "failed"]),
            )
            .values(status="superseded")
        )
        await self.session.execute(
            insert(IndexJob)
            .values(
                id=uuid4(),
                user_id=self.user_id,
                content_hash=content_hash,
                filename=filename,
                device_path=device_path,
                status="queued",
                attempts=0,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "content_hash", "device_path"])
        )
        result = await self.session.execute(
            self.scoped().where(
                IndexJob.content_hash == content_hash, IndexJob.device_path == device_path
            )
        )
        job = result.scalar_one()
        if job.status == "superseded":
            job.status, job.attempts, job.error = "queued", 0, None
            job.retry_at = datetime.now(UTC)
        return job

    async def recent(self, limit: int = 100, offset: int = 0) -> list[IndexJob]:
        return list(
            (
                await self.session.execute(
                    self.scoped()
                    .order_by(IndexJob.updated_at.desc(), IndexJob.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).scalars()
        )

    async def counts(self) -> dict[str, int]:
        rows = await self.session.execute(
            self.scoped().with_only_columns(IndexJob.status, func.count()).group_by(IndexJob.status)
        )
        return dict(rows.all())

    async def next(self) -> IndexJob | None:
        # The transaction holds this row lock through ingestion. Worker termination
        # rolls back, making the same durable job eligible on the next poll.
        return (
            await self.session.execute(
                self.scoped()
                .where(
                    IndexJob.status.in_(["queued", "processing"]),
                    IndexJob.retry_at <= datetime.now(UTC),
                )
                .order_by(IndexJob.retry_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
        ).scalar_one_or_none()

    async def reconcile(self, paths: set[str], prefix: str | None) -> None:
        pending = (
            await self.session.execute(
                self.scoped().where(IndexJob.status.in_(["queued", "processing", "failed"]))
            )
        ).scalars()
        for job in pending:
            if (
                prefix is None or job.device_path.startswith(prefix)
            ) and job.device_path not in paths:
                job.status = "superseded"

    async def delete_for_hash(self, content_hash: str) -> None:
        from sqlalchemy import delete

        await self.session.execute(
            delete(IndexJob).where(
                IndexJob.user_id == self.user_id, IndexJob.content_hash == content_hash
            )
        )

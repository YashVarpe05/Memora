"""Persistent, hashed device credentials. Each credential owns an isolated library."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

PAIRING_CODE_BYTES = 16
DEVICE_TOKEN_BYTES = 32
PAIRING_TTL = timedelta(minutes=5)


@dataclass(frozen=True)
class Pairing:
    code: str
    expires_at: datetime

    def expired(self, now: datetime | None = None) -> bool:
        return (now or datetime.now(UTC)) >= self.expires_at


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class PairingStore:
    def __init__(self, path: str = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS codes (hash TEXT PRIMARY KEY, expires REAL)")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS devices (hash TEXT PRIMARY KEY, id TEXT UNIQUE)"
        )
        self.db.commit()

    def start(self, now: datetime | None = None) -> Pairing:
        now = now or datetime.now(UTC)
        pairing = Pairing(secrets.token_urlsafe(PAIRING_CODE_BYTES), now + PAIRING_TTL)
        with self.db:
            self.db.execute("DELETE FROM codes WHERE expires <= ?", (now.timestamp(),))
            self.db.execute(
                "INSERT INTO codes VALUES (?, ?)",
                (digest(pairing.code), pairing.expires_at.timestamp()),
            )
        return pairing

    def claim(self, code: str, now: datetime | None = None) -> str | None:
        with self.db:
            row = self.db.execute(
                "DELETE FROM codes WHERE hash = ? RETURNING expires", (digest(code),)
            ).fetchone()
            if row is None or row[0] <= (now or datetime.now(UTC)).timestamp():
                return None
            token = secrets.token_urlsafe(DEVICE_TOKEN_BYTES)
            self.db.execute("INSERT INTO devices VALUES (?, ?)", (digest(token), str(uuid4())))
        return token

    def identity(self, token: str | None) -> UUID | None:
        if not token:
            return None
        row = self.db.execute("SELECT id FROM devices WHERE hash = ?", (digest(token),)).fetchone()
        return UUID(row[0]) if row else None

    def identities(self) -> list[UUID]:
        return [UUID(row[0]) for row in self.db.execute("SELECT id FROM devices")]

    def is_paired(self, token: str | None) -> bool:
        return self.identity(token) is not None

    def revoke_all(self) -> int:
        count = self.device_count
        with self.db:
            self.db.execute("DELETE FROM devices")
            self.db.execute("DELETE FROM codes")
        return count

    @property
    def device_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM devices").fetchone()[0]


_store: PairingStore | None = None


def store() -> PairingStore:
    global _store
    if _store is None:
        from memora.config import get_settings
        from memora.paths import repo_root

        path = Path(get_settings().pairing_store)
        _store = PairingStore(str(path if path.is_absolute() else repo_root() / path))
    return _store

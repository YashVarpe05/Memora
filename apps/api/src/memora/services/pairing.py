"""Pairing a phone with the machine that holds the documents.

**This is a privacy property, not a convenience.** The demo runs over a phone hotspot, and
the API serves the user's own documents - Aadhaar photos, marksheets, private messages.
Anyone else on that network can reach the laptop's port. Without a token, "nothing leaves
devices the user owns" is false the moment a second person joins the hotspot, and the
architecture note in `prompts/capacitor-auto-scan.md` §1 stops being true.

Two tokens, because they have different lifetimes and different exposure:

- a **pairing code**, short, short-lived, displayed as a QR on the laptop. It is visible
  to anyone who can see the screen, so it expires in minutes and is single-use.
- a **device token**, long, long-lived, held only by the phone in `SecureStorage`. It never
  appears on screen, in a URL, or in a log.

Deliberately NOT user authentication. `current_user_id` is still the server-derived
identity and phase 5 replaces it. This answers a narrower question - *is this request from
a device the owner paired?* - and answering it does not require answering the other one.

In-memory on purpose. Pairings live as long as the process, which is exactly the demo's
lifetime, and a device token that does not survive a restart is a smaller problem than one
persisted somewhere that has to be secured.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# Long enough that guessing is hopeless, short enough to render as a readable QR.
PAIRING_CODE_BYTES = 6
DEVICE_TOKEN_BYTES = 32

# The QR is on a screen in a room. It should stop working before the room empties.
PAIRING_TTL = timedelta(minutes=5)


@dataclass(frozen=True)
class Pairing:
    code: str
    expires_at: datetime

    def expired(self, now: datetime | None = None) -> bool:
        return (now or datetime.now(UTC)) >= self.expires_at


class PairingStore:
    """Outstanding pairing codes, and the device tokens they became."""

    def __init__(self) -> None:
        self._pending: dict[str, Pairing] = {}
        self._devices: set[str] = set()

    def start(self, now: datetime | None = None) -> Pairing:
        """A new code for the QR. Any previous unclaimed code stays valid until it
        expires - showing a second QR should not silently break the first."""
        pairing = Pairing(
            code=secrets.token_urlsafe(PAIRING_CODE_BYTES),
            expires_at=(now or datetime.now(UTC)) + PAIRING_TTL,
        )
        self._pending[pairing.code] = pairing
        return pairing

    def claim(self, code: str, now: datetime | None = None) -> str | None:
        """Exchange a pairing code for a device token. Single use.

        Returns None for an unknown, expired, or already-claimed code - the caller must
        not be able to tell which, so a wrong guess reveals nothing about a right one.
        """
        pairing = self._pending.pop(code, None)
        if pairing is None or pairing.expired(now):
            return None
        token = secrets.token_urlsafe(DEVICE_TOKEN_BYTES)
        self._devices.add(token)
        return token

    def is_paired(self, token: str | None) -> bool:
        if not token:
            return False
        # Constant-time against every known token: a timing difference would leak how
        # much of a guess was correct.
        return any(secrets.compare_digest(token, known) for known in self._devices)

    def revoke_all(self) -> int:
        """Unpair every device. The user-facing panic button."""
        count = len(self._devices)
        self._devices.clear()
        self._pending.clear()
        return count

    @property
    def device_count(self) -> int:
        return len(self._devices)


_store = PairingStore()


def store() -> PairingStore:
    return _store

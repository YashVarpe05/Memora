"""Pairing a phone, and the enforcement that makes the token mean something.

The demo runs over a phone hotspot. The API serves the owner's Aadhaar photos, marksheets
and private messages, and anyone else who joins that network can reach the port. Without
enforcement, "nothing leaves devices the user owns" is false the moment a second person
connects — so these are privacy tests, not convenience tests.
"""

from datetime import UTC, datetime, timedelta

import pytest

from memora.services.pairing import PAIRING_TTL, PairingStore


@pytest.fixture
def pairings():
    return PairingStore()


def test_a_code_can_be_claimed_once(pairings):
    code = pairings.start().code

    first = pairings.claim(code)
    second = pairings.claim(code)

    assert first, "a fresh code must produce a device token"
    assert second is None, "a claimed code must not work twice"


def test_an_expired_code_is_refused(pairings):
    code = pairings.start().code
    later = datetime.now(UTC) + PAIRING_TTL + timedelta(seconds=1)

    assert pairings.claim(code, now=later) is None


def test_an_unknown_code_is_refused(pairings):
    assert pairings.claim("not-a-real-code") is None


def test_unknown_expired_and_claimed_are_indistinguishable(pairings):
    """All three return None. Telling them apart would let a guesser learn which half of
    a guess was right."""
    claimed = pairings.start().code
    pairings.claim(claimed)
    expired = pairings.start().code
    later = datetime.now(UTC) + PAIRING_TTL + timedelta(seconds=1)

    assert pairings.claim(claimed) is None
    assert pairings.claim(expired, now=later) is None
    assert pairings.claim("invented") is None


def test_tokens_are_unique_per_device(pairings):
    a = pairings.claim(pairings.start().code)
    b = pairings.claim(pairings.start().code)

    assert a != b
    assert pairings.is_paired(a) and pairings.is_paired(b)


def test_an_unpaired_token_is_rejected(pairings):
    pairings.claim(pairings.start().code)

    assert not pairings.is_paired("some-other-token")
    assert not pairings.is_paired("")
    assert not pairings.is_paired(None)


def test_revoke_unpairs_everything(pairings):
    token = pairings.claim(pairings.start().code)
    pending = pairings.start().code

    pairings.revoke_all()

    assert not pairings.is_paired(token)
    assert pairings.claim(pending) is None, "a pending code must not survive a revoke"
    assert pairings.device_count == 0


def test_showing_a_second_qr_does_not_break_the_first(pairings):
    """Two codes outstanding is normal - the user taps the button twice. Invalidating
    the first would make the visible QR silently stop working."""
    first = pairings.start().code
    pairings.start()

    assert pairings.claim(first) is not None


# --- enforcement, through the API ---


async def test_the_dependency_rejects_a_non_loopback_client_without_a_token():
    """Driven directly, because the ASGI test client always presents a loopback peer."""
    from fastapi import HTTPException
    from starlette.datastructures import Headers

    from memora.api.routers.pairing import require_paired_device
    from memora.config import Settings

    class FakeRequest:
        client = type("C", (), {"host": "192.168.1.50"})()
        headers = Headers({})

    settings = Settings(require_pairing=True)
    store = PairingStore()

    with pytest.raises(HTTPException) as raised:
        await require_paired_device(FakeRequest(), settings, store)

    assert raised.value.status_code == 401


async def test_the_dependency_accepts_a_paired_token():
    from starlette.datastructures import Headers

    from memora.api.routers.pairing import require_paired_device
    from memora.config import Settings

    store = PairingStore()
    token = store.claim(store.start().code)

    class FakeRequest:
        client = type("C", (), {"host": "192.168.1.50"})()
        headers = Headers({"authorization": f"Bearer {token}"})

    # Returns None rather than raising.
    assert await require_paired_device(FakeRequest(), Settings(require_pairing=True), store) is None


async def test_loopback_never_needs_to_pair():
    """The laptop's own browser is the owner sitting at the machine. Requiring it to
    pair would mean scanning a QR with the screen the QR is displayed on."""
    from starlette.datastructures import Headers

    from memora.api.routers.pairing import require_paired_device
    from memora.config import Settings

    class FakeRequest:
        client = type("C", (), {"host": "127.0.0.1"})()
        headers = Headers({})

    assert await require_paired_device(FakeRequest(), Settings(require_pairing=True), PairingStore()) is None


async def test_health_and_pairing_are_reachable_before_pairing(api):
    """The phone must be able to find the server and claim a code before it has a token.
    Neither endpoint returns anything private."""
    assert (await api.get("/health")).status_code == 200
    assert (await api.post("/pair/start")).status_code == 200

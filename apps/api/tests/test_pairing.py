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

    settings = Settings(require_pairing=True)
    assert await require_paired_device(FakeRequest(), settings, PairingStore()) is None


async def test_health_and_pairing_are_reachable_before_pairing(api):
    """The phone must be able to find the server and claim a code before it has a token.
    Neither endpoint returns anything private."""
    assert (await api.get("/health")).status_code == 200
    assert (await api.post("/pair/start")).status_code == 200


# --- the operator boundary ---
#
# These exist because the router shipped without them. /pair/start and /pair/claim were
# both open, so a phone on the hotspot could mint a code and claim it: two unauthenticated
# requests to a genuine device token, and require_paired_device would then admit it
# forever. The whole pairing mechanism enforced nothing. The suite did not notice because
# the ASGI client always presents a loopback peer, so every route looks local in a test.


def _request_from(host: str, headers: dict[str, str] | None = None):
    from starlette.datastructures import Headers

    class FakeRequest:
        client = type("C", (), {"host": host})()

    FakeRequest.headers = Headers(headers or {})
    return FakeRequest()


async def test_a_device_on_the_network_cannot_mint_a_pairing_code():
    """The bypass. Minting is an operator power, not a network power."""
    from fastapi import HTTPException

    from memora.api.routers.pairing import require_local_operator
    from memora.config import Settings

    with pytest.raises(HTTPException) as raised:
        await require_local_operator(_request_from("192.168.1.50"), Settings(require_pairing=True))

    assert raised.value.status_code == 403


async def test_a_device_on_the_network_cannot_revoke_pairings():
    """Otherwise anyone on the hotspot can unpair the owner's phone mid-demo."""
    from fastapi import HTTPException

    from memora.api.routers.pairing import require_local_operator
    from memora.config import Settings

    with pytest.raises(HTTPException):
        await require_local_operator(_request_from("10.29.51.7"), Settings(require_pairing=True))


async def test_the_operator_at_the_machine_may_mint():
    from memora.api.routers.pairing import require_local_operator
    from memora.config import Settings

    local = _request_from("127.0.0.1")
    assert await require_local_operator(local, Settings(require_pairing=True)) is None




# --- the same boundary, driven as real HTTP from a phone-like address ---
#
# The tests above drive the dependency directly; these drive the whole app. httpx's
# ASGITransport takes the client peer, so a request can arrive from 192.168.1.50 instead
# of the loopback the default presents - which is what made this class of bug invisible.


def _from_the_network(app):
    from httpx import ASGITransport, AsyncClient

    return AsyncClient(
        transport=ASGITransport(app=app, client=("192.168.1.50", 51111)),
        base_url="http://memora.local",
    )


def _from_the_laptop(app):
    from httpx import ASGITransport, AsyncClient

    return AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 51112)),
        base_url="http://memora.local",
    )


async def test_the_self_pairing_bypass_is_closed():
    """The bug this whole section exists for, end to end.

    Shipped, a phone on the hotspot could mint a code and claim it - two unauthenticated
    requests to a genuine device token, after which every document endpoint admitted it.
    """
    from memora.main import create_app

    app = create_app()
    async with _from_the_network(app) as phone:
        minted = await phone.post("/pair/start")

    assert minted.status_code == 403, "a device on the network must not mint its own code"


async def test_a_phone_can_still_claim_a_code_the_laptop_minted():
    """The fix must not close the bootstrap. The phone has no token at this point, so
    /pair/claim has to answer a stranger - that is the one endpoint that must stay open."""
    from memora.main import create_app

    app = create_app()
    async with _from_the_laptop(app) as laptop:
        started = await laptop.post("/pair/start")
    assert started.status_code == 200

    async with _from_the_network(app) as phone:
        claimed = await phone.post("/pair/claim", json={"code": started.json()["code"]})

    assert claimed.status_code == 200, "the phone must be able to claim from the network"
    assert claimed.json()["device_token"]


async def test_the_network_cannot_revoke_or_read_status():
    from memora.main import create_app

    app = create_app()
    async with _from_the_network(app) as phone:
        assert (await phone.post("/pair/revoke")).status_code == 403
        assert (await phone.get("/pair/status")).status_code == 403


async def test_the_network_cannot_reach_search_without_a_paired_token():
    """Refused before the route body runs, so this needs no database - which is the
    point: enforcement that depended on Postgres being up would be enforcement that
    silently skipped itself, and this suite has shipped that mistake before."""
    from memora.main import create_app

    app = create_app()
    async with _from_the_network(app) as phone:
        none = await phone.post("/search", json={"query": "aadhaar", "limit": 3})
        invented = await phone.post(
            "/search",
            json={"query": "aadhaar", "limit": 3},
            headers={"Authorization": "Bearer not-a-real-token"},
        )

    assert none.status_code == 401, "no token must not reach the corpus"
    assert invented.status_code == 401, "an invented token must not reach the corpus"


async def test_a_paired_phone_gets_past_the_door(app, api):
    """The other half. Without it the suite proves only that everything is refused,
    which a brick wall also does.

    Takes `api` for its doubles and database session - and, just as importantly, for its
    skip: `app` alone is deliberately DB-free, so this test would raise
    ConnectionRefusedError with the containers down instead of skipping, turning "Postgres
    is off" into a red suite that looks like a broken feature. The client is built here
    rather than reused from `api` because that one presents a loopback peer, which is the
    exact condition this test has to avoid.
    """
    async with _from_the_laptop(app) as laptop:
        code = (await laptop.post("/pair/start")).json()["code"]
    async with _from_the_network(app) as phone:
        token = (await phone.post("/pair/claim", json={"code": code})).json()["device_token"]
        accepted = await phone.post(
            "/search",
            json={"query": "aadhaar", "limit": 3},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert accepted.status_code != 401, "the paired phone must get past the door"


# --- the origin the phone actually calls from ---


async def test_the_capacitor_webview_origin_survives_a_cors_preflight():
    """The phone is not a same-origin caller and never was.

    A Capacitor WebView serves the bundled app from `http://localhost` with no port, so
    every request it makes to the laptop is cross-origin and POSTing JSON triggers a
    preflight first. With only `http://localhost:5173` allowed, that preflight returned
    400 "Disallowed CORS origin", fetch threw, and the app displayed "Could not reach your
    computer" - a network message for a configuration fault, which sent the debugging to
    entirely the wrong place.

    Asserted per origin rather than on the list, so deleting an entry fails here.
    """
    from memora.main import create_app

    app = create_app()
    for origin in ("http://localhost", "https://localhost", "capacitor://localhost"):
        async with _from_the_network(app) as phone:
            preflight = await phone.options(
                "/pair/claim",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )

        assert preflight.status_code == 200, f"{origin} was refused: {preflight.text}"
        assert preflight.headers.get("access-control-allow-origin") == origin

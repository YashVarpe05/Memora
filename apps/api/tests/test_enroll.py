"""A phone built with the enrollment secret can join itself; nothing else can."""

import secrets

import pytest

from memora.api.routers import pairing
from memora.config import get_settings
from memora.services.pairing import AttemptLimiter, PairingStore

SECRET = secrets.token_urlsafe(24)


@pytest.fixture
def enrolling(app, monkeypatch):
    """The real pairing store (in memory), the real endpoint, a fresh limiter."""
    store = PairingStore()
    limiter = AttemptLimiter(limit=3, lockout=600.0)
    monkeypatch.setattr(get_settings(), "enrollment_secret", SECRET)
    app.dependency_overrides[pairing.get_store] = lambda: store
    app.dependency_overrides[pairing.enroll_limiter] = lambda: limiter
    yield store, limiter
    app.dependency_overrides.pop(pairing.get_store, None)
    app.dependency_overrides.pop(pairing.enroll_limiter, None)


async def test_the_endpoint_is_off_unless_a_secret_is_configured(client, app, monkeypatch):
    monkeypatch.setattr(get_settings(), "enrollment_secret", None)
    response = await client.post("/pair/enroll", json={"secret": "anything"})
    assert response.status_code == 404


async def test_the_right_secret_returns_a_token_that_identifies_a_new_library(client, enrolling):
    store, _ = enrolling
    first = await client.post("/pair/enroll", json={"secret": SECRET})
    second = await client.post("/pair/enroll", json={"secret": SECRET})
    assert first.status_code == second.status_code == 200
    tokens = [first.json()["device_token"], second.json()["device_token"]]
    assert tokens[0] != tokens[1]
    identities = {store.identity(token) for token in tokens}
    assert len(identities) == 2 and None not in identities
    assert store.device_count == 2


async def test_a_wrong_secret_is_refused_generically_and_creates_nothing(client, enrolling):
    store, _ = enrolling
    response = await client.post("/pair/enroll", json={"secret": "not-the-secret"})
    assert response.status_code == 401
    assert SECRET not in response.text
    assert store.device_count == 0


async def test_guessing_locks_the_endpoint_even_for_the_right_secret(client, enrolling):
    for _ in range(3):
        assert (await client.post("/pair/enroll", json={"secret": "guess"})).status_code == 401
    locked = await client.post("/pair/enroll", json={"secret": SECRET})
    assert locked.status_code == 429


async def test_a_success_resets_the_failure_count(client, enrolling):
    _, limiter = enrolling
    await client.post("/pair/enroll", json={"secret": "guess"})
    await client.post("/pair/enroll", json={"secret": "guess"})
    assert (await client.post("/pair/enroll", json={"secret": SECRET})).status_code == 200
    for _ in range(2):
        await client.post("/pair/enroll", json={"secret": "guess"})
    assert not limiter.locked()


def test_the_limiter_unlocks_after_its_lockout_period():
    now = [0.0]
    limiter = AttemptLimiter(limit=2, lockout=60.0, clock=lambda: now[0])
    limiter.fail()
    limiter.fail()
    assert limiter.locked()
    now[0] = 61.0
    assert not limiter.locked()

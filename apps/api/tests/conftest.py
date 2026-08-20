"""Test fixtures.

Deliberately no database here. Phase-1 tests must pass before `docker compose up`,
so nothing in this file may require a live service.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from memora.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

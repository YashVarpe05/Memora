"""The per-owner guardrail must be impossible to bypass by accident."""

import uuid

import pytest

from memora.repositories.base import BaseRepository


def test_repository_rejects_missing_user_id():
    with pytest.raises(ValueError, match="requires a user_id"):
        BaseRepository(session=None, user_id=None)


def test_repository_rejects_non_uuid_user_id():
    """A raw string from a request body must not be accepted as an owner id."""
    with pytest.raises(TypeError):
        BaseRepository(session=None, user_id="00000000-0000-0000-0000-000000000000")


def test_repository_accepts_uuid_user_id():
    repo = BaseRepository(session=None, user_id=uuid.uuid4())
    assert isinstance(repo.user_id, uuid.UUID)

"""Blob storage. Content-addressed, per-owner, no path derived from user input."""

import uuid

import pytest

from memora.services.storage import BlobStore, make_thumbnail, sha256_of

from support import make_pdf, make_png

USER_A = uuid.uuid4()
USER_B = uuid.uuid4()


@pytest.fixture
def store(tmp_path):
    return BlobStore(root=tmp_path)


def test_put_then_read_returns_the_same_bytes(store):
    data = b"the original document bytes"

    stored = store.put(USER_A, data)

    assert stored.content_hash == sha256_of(data)
    assert stored.byte_size == len(data)
    assert store.read(USER_A, stored.content_hash) == data


def test_same_bytes_from_one_user_deduplicate(store):
    data = b"identical"

    first = store.put(USER_A, data)
    second = store.put(USER_A, data)

    assert first.content_hash == second.content_hash
    assert not first.deduplicated
    assert second.deduplicated


def test_two_users_never_share_a_blob(store):
    """A shared blob is a cross-user inference channel.

    If storage were globally content-addressed, user B uploading a file and seeing it
    deduplicate would tell them user A already holds it.
    """
    data = b"byte identical content"

    a = store.put(USER_A, data)
    b = store.put(USER_B, data)

    assert a.content_hash == b.content_hash
    assert not b.deduplicated, "user B's upload must not deduplicate against user A"
    assert store.path(USER_A, a.content_hash) != store.path(USER_B, b.content_hash)
    assert store.path(USER_A, a.content_hash).exists()
    assert store.path(USER_B, b.content_hash).exists()


def test_a_user_cannot_read_another_users_blob(store):
    stored = store.put(USER_A, b"private")

    assert not store.exists(USER_B, stored.content_hash)


@pytest.mark.parametrize(
    "bad",
    [
        "../../etc/passwd",
        "not-a-hash",
        "ABCDEF0123456789" * 4,  # uppercase
        "0" * 63,
        "0" * 65,
        "",
    ],
)
def test_a_malformed_hash_never_reaches_the_filesystem(store, bad):
    with pytest.raises(ValueError, match="64 lowercase hex"):
        store.path(USER_A, bad)


def test_user_id_must_be_a_uuid(store):
    with pytest.raises(TypeError):
        store.path("../other-user", sha256_of(b"x"))


def test_delete_removes_blob_and_thumbnail(store):
    stored = store.put(USER_A, b"content")
    store.put_thumbnail(USER_A, stored.content_hash, b"thumb")
    assert store.thumbnail_path(USER_A, stored.content_hash).exists()

    store.delete(USER_A, stored.content_hash)

    assert not store.path(USER_A, stored.content_hash).exists()
    assert not store.thumbnail_path(USER_A, stored.content_hash).exists()


def test_deleting_a_missing_blob_is_not_an_error(store):
    store.delete(USER_A, sha256_of(b"never stored"))


def test_purge_user_removes_everything_they_own(store):
    store.put(USER_A, b"one")
    store.put(USER_A, b"two")
    kept = store.put(USER_B, b"three")

    store.purge_user(USER_A)

    assert not (store._user_dir(USER_A)).exists()
    assert store.exists(USER_B, kept.content_hash)


def test_no_partial_file_is_left_at_the_hash_address(store):
    """Writes stage then rename, so a hash never addresses a truncated file."""
    stored = store.put(USER_A, b"x" * 5000)
    leftovers = list(store.path(USER_A, stored.content_hash).parent.glob("*.partial"))

    assert leftovers == []


def test_thumbnail_is_generated_for_an_image():
    thumb = make_thumbnail(make_png(800, 600), "image/png")

    assert thumb is not None
    assert thumb[:3] == bytes([0xFF, 0xD8, 0xFF]), "expected a JPEG"


def test_thumbnail_is_generated_for_a_pdf():
    thumb = make_thumbnail(make_pdf(["hello"]), "application/pdf")

    assert thumb is not None
    assert thumb[:3] == bytes([0xFF, 0xD8, 0xFF])


def test_unpreviewable_bytes_return_none_rather_than_raising():
    """A missing preview must never fail an upload."""
    assert make_thumbnail(b"not an image at all", "image/png") is None

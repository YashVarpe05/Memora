"""Project locations must not depend on the directory you are standing in.

Two bugs came from the same mistake, and both were found by accident rather than by a
test:

- `blob_root` was a relative path resolved against the working directory, so an ingest
  run from apps/api wrote real documents to apps/api/data/blobs - one level below where
  the ignore rule reached. Fifteen personal documents were committed.
- The eval harness used `resolve()` for its defaults, which prefers whatever exists
  relative to the current directory. A stray data/corpus under apps/api made the
  inspector report one file instead of fifteen, and overwrite the gold-set draft with it.

`anchored()` is for defaults and always returns the same location. `resolve()` is for
paths a person typed, where cwd-relative is what they meant.
"""

import uuid
from pathlib import Path

from memora.paths import anchored, repo_root, resolve
from memora.services.storage import BlobStore


def test_anchored_ignores_the_working_directory(tmp_path, monkeypatch):
    expected = repo_root() / "data/corpus"

    monkeypatch.chdir(tmp_path)
    assert anchored("data/corpus") == expected

    (tmp_path / "data" / "corpus").mkdir(parents=True)
    assert anchored("data/corpus") == expected, "an existing local copy must not win"


def test_anchored_is_stable_from_a_subdirectory(monkeypatch):
    from_root = anchored("data/blobs")

    monkeypatch.chdir(repo_root() / "apps" / "api")
    assert anchored("data/blobs") == from_root


def test_resolve_still_prefers_a_path_the_user_typed(tmp_path, monkeypatch):
    """An explicit argument means what it says relative to where it was typed."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mycorpus").mkdir()

    assert resolve(Path("mycorpus")) == Path("mycorpus")


def test_resolve_falls_back_to_the_repo_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert resolve(Path("docs/PRODUCT.md")) == repo_root() / "docs/PRODUCT.md"


def test_blob_store_root_does_not_move_with_the_cwd(tmp_path, monkeypatch):
    """The bug that leaked documents: a second blob tree under apps/api."""
    from_root = BlobStore()._root

    monkeypatch.chdir(repo_root() / "apps" / "api")
    assert BlobStore()._root == from_root

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "blobs").mkdir(parents=True)
    assert BlobStore()._root == from_root, "a local data/blobs must not capture uploads"


def test_blob_paths_stay_under_the_anchored_root():
    store = BlobStore()
    user = uuid.uuid4()
    digest = "a" * 64

    assert store.path(user, digest).is_relative_to(store._root)
    assert store.thumbnail_path(user, digest).is_relative_to(store._root)

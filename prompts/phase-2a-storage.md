# Phase 2a — blob storage

Split out of `/search` because a wrong storage scheme costs a migration, while search on
settled storage is straightforward.

## Approved

- Content-addressed at `data/blobs/<user_id>/<sha256>`. Path from the hash only, never
  from the uploaded filename.
- `Memory` gets a blob reference; the uploaded filename stays display metadata.
- Nullable `page` on `chunks`, populated during extraction. Cheap now, a backfill later.
- Deletion removes the blob, the rows and the vectors, and is tested — verifiable erasure
  is a `PRODUCT.md` claim.
- Dedup within a user. **Never across users**, even on byte-identical content.

## Two decisions this plan makes

**1. The database stores a hash, not a path.**

The obvious schema is `blob_path VARCHAR`. Storing the path instead of deriving it means
the database holds a filesystem path that some later code will join, and a row is a
thing an attacker might one day influence. Deriving `blob_root / user_id / hash` from
three values the server already trusts means there is no path in the database to poison,
and relocating the blob root is a config change rather than a data migration.

So: `content_hash`, `byte_size`, `mime_type` on `Memory`; the path is computed.

**2. Thumbnails generate at ingest.**

On-demand is tempting - no disk cost, nothing generated that is never viewed. But the
result grid is the product's face: the user recognises their Aadhaar card by looking at
it, so the first paint of a search would trigger N renders at once, repeated on every
search. That is the wrong latency to pay, in the wrong place.

Ingest already pays for OCR, which is orders of magnitude slower than a 320px resize, so
the marginal upload cost is close to nothing. One code path, and the thumbnail exists
before anything can ask for it.

**3. Cross-user dedup is prevented by the schema, not by a code path.**

A globally content-addressed store would let user B learn that user A holds a file, just
by observing that their upload deduplicated. Two mechanisms, both structural: the user id
is a path component, so two users cannot land on the same file; and the uniqueness
constraint is on `(user_id, content_hash)`, so the database cannot express a shared blob
even if the storage layer were rewritten.

## Files

**Create** `services/storage.py`, `migrations/versions/0002_blobs_and_pages.py`,
`api/routers/files.py`, `tests/test_storage.py`, `tests/test_deletion.py`

**Modify** `db/models/{memory,chunk}.py`, `services/{extraction,chunking}.py`,
`api/routers/uploads.py`, `repositories/memory.py`, `config.py`, `.gitignore`

## Acceptance criteria

1. Uploading stores the bytes; `GET /memories/{id}/file` returns them byte-identical.
2. `GET /memories/{id}/thumbnail` returns an image for both a PDF and an image upload.
3. Re-uploading the same bytes as the same user creates no second blob.
4. The same bytes uploaded by two users produce two blobs, in two directories.
5. Another user's memory 404s on both file endpoints.
6. `DELETE /memories/{id}` removes rows, vectors, blob and thumbnail. Verified on disk.
7. A PDF chunk carries the page it came from; an image chunk carries null.
8. A hash that is not 64 hex characters is rejected before it reaches the filesystem.

## Verify

```
cd apps/api && uv run pytest && uv run ruff check . && uv run alembic upgrade head
```

Then upload a corpus file, fetch its `file_url`, and compare the bytes to the original.

## Note for BASELINE.md

The `/search` over-fetch bound — a document whose only matching chunk falls outside the
fetch window is invisible, and the risk grows with corpus size — belongs in `BASELINE.md`
as a known bound when the numbers are recorded, not only in the plan. It is the kind of
limitation an examiner finds by asking "what happens at 10,000 documents", and it reads
very differently as a documented bound than as a discovery.

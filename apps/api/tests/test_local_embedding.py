"""Provider contract tests; real semantic quality is a separate opt-in model smoke."""

import pytest

from memora.services.embedding import LocalE5Embedder, embed_query, embedding_fingerprint
from memora.services.masking import mask_all, mask_identifiers

MODEL = "intfloat/multilingual-e5-base"
REVISION = "d128750597153bb5987e10b1c3493a34e5a4502a"


class Result:
    def __init__(self, count):
        self.count = count

    def tolist(self):
        return [[2.0] + [0.0] * 767 for _ in range(self.count)]


class Encoder:
    def __init__(self):
        self.calls = []

    def encode(self, texts, **kwargs):
        self.calls.append((texts, kwargs))
        return Result(len(texts))


async def test_local_model_uses_correct_prefixes_masking_and_normalization():
    provider = LocalE5Embedder(MODEL, REVISION)
    encoder = Encoder()
    provider._model = encoder
    assert not provider.ready
    passages = await provider.embed(mask_all(["Aadhaar PAN ABCDE1234F", "गुणपत्रिका"]))
    query = await embed_query(provider, mask_identifiers("माझे आधार कार्ड"))
    assert encoder.calls[0][0][0].startswith("passage: Aadhaar PAN ")
    assert "ABCDE1234F" not in encoder.calls[0][0][0]
    assert encoder.calls[0][0][1] == "passage: गुणपत्रिका"
    assert encoder.calls[1][0] == ["query: माझे आधार कार्ड"]
    assert encoder.calls[0][1]["normalize_embeddings"] is True
    assert passages[0] == query == [1.0] + [0.0] * 767
    assert provider.ready


async def test_local_embedding_rejects_raw_unmasked_input():
    provider = LocalE5Embedder(MODEL, REVISION)
    with pytest.raises(TypeError, match="MaskedText"):
        await provider.embed(["unsafe raw text"])
    assert not provider.ready


def test_fingerprint_tracks_revision_and_rejects_mutable_revision():
    old = LocalE5Embedder(MODEL, REVISION)
    new = LocalE5Embedder(MODEL, "0" * 40)
    assert embedding_fingerprint(old) != embedding_fingerprint(new)
    assert "query-passage" in embedding_fingerprint(old)
    with pytest.raises(ValueError, match="immutable"):
        LocalE5Embedder(MODEL, "main")
    with pytest.raises(ValueError, match="768"):
        LocalE5Embedder(MODEL, REVISION, dims=384)


async def test_local_empty_batch_does_not_load_model():
    provider = LocalE5Embedder(MODEL, REVISION)
    assert await provider.embed([]) == []
    assert not provider.ready

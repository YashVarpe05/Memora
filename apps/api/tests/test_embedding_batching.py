"""Provider batch limits are the embedder's problem, not the caller's.

Gemini rejects more than 100 items in one embed request with a 400. One calendar export
is 353 events, so this is reached by the first realistic document rather than at scale -
and it was found by ingesting the real corpus, not by the suite, because the test double
has no such limit.
"""

from memora.services.embedding import MAX_BATCH, GeminiEmbedder
from memora.services.masking import mask_all


class StubClient:
    """Stands in for genai.Client, and enforces the limit the real API enforces."""

    def __init__(self) -> None:
        self.batch_sizes: list[int] = []
        self.aio = self

    @property
    def models(self):
        return self

    async def embed_content(self, *, model, contents, config):
        if len(contents) > MAX_BATCH:
            raise ValueError(f"at most {MAX_BATCH} requests can be in one batch")
        self.batch_sizes.append(len(contents))
        dims = config.output_dimensionality
        return type(
            "R",
            (),
            {
                "embeddings": [
                    type("E", (), {"values": [1.0] + [0.0] * (dims - 1)})()
                    for _ in contents
                ]
            },
        )()


def embedder_with(stub: StubClient) -> GeminiEmbedder:
    embedder = GeminiEmbedder(api_key="test", model="m", dims=768)
    embedder._client = stub
    return embedder


async def test_a_large_document_is_split_into_provider_sized_batches():
    stub = StubClient()
    texts = mask_all([f"event number {i}" for i in range(353)])

    vectors = await embedder_with(stub).embed(texts)

    assert len(vectors) == 353, "every input must get a vector back"
    assert stub.batch_sizes == [32] * 11 + [1]


async def test_a_small_document_is_a_single_call():
    stub = StubClient()

    await embedder_with(stub).embed(mask_all(["one", "two"]))

    assert stub.batch_sizes == [2]


async def test_an_exact_multiple_does_not_send_an_empty_batch():
    stub = StubClient()

    await embedder_with(stub).embed(mask_all([f"x{i}" for i in range(200)]))

    assert stub.batch_sizes == [32] * 6 + [8]


async def test_vectors_come_back_unit_length():
    import math

    stub = StubClient()

    vectors = await embedder_with(stub).embed(mask_all(["a"]))

    assert math.isclose(math.sqrt(sum(v * v for v in vectors[0])), 1.0)


class ThrottlingClient(StubClient):
    """Rejects the first N calls with the provider's rate-limit error."""

    def __init__(self, fail_times: int) -> None:
        super().__init__()
        self.remaining_failures = fail_times
        self.attempts = 0

    async def embed_content(self, *, model, contents, config):
        self.attempts += 1
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise RuntimeError(
                "429 RESOURCE_EXHAUSTED. Quota exceeded. Please retry in 0.01s."
            )
        return await super().embed_content(model=model, contents=contents, config=config)


async def test_rate_limiting_is_retried_not_raised():
    """The free tier caps embed requests per minute, and a 353-event calendar exceeds
    it during one upload. A 429 is expected traffic here, not a failure."""
    stub = ThrottlingClient(fail_times=2)

    vectors = await embedder_with(stub).embed(mask_all(["a", "b"]))

    assert len(vectors) == 2
    assert stub.attempts == 3


async def test_a_non_rate_limit_error_is_not_retried():
    """Retrying a 400 just makes the same mistake six times."""
    import pytest

    class Broken(StubClient):
        async def embed_content(self, **kwargs):
            raise RuntimeError("400 INVALID_ARGUMENT")

    with pytest.raises(RuntimeError, match="400"):
        await embedder_with(Broken()).embed(mask_all(["a"]))


async def test_the_server_supplied_delay_is_used():
    from memora.services.embedding import DEFAULT_BACKOFF_SECONDS, _retry_delay

    assert _retry_delay(RuntimeError("please retry in 23.4s")) == 24.4
    assert _retry_delay(RuntimeError("no hint here")) == DEFAULT_BACKOFF_SECONDS

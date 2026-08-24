"""Silent degradation to dense-only is the worst failure this system can have.

When the daily generate quota runs out, stage 1 falls back to passthrough on every
search. Retrieval keeps working and keeps returning results — just measurably worse ones
(Recall@1 0.947 -> 0.842 on the gold set, and the calendar starts winning queries it
should not). Nothing about the response looks wrong. These tests exist so that failure
can never be invisible again: it happened once during measurement and was nearly written
up as a result.
"""

import pytest
from support import FakeStageOne, make_png

from memora.api.routers import search as search_router
from memora.services.stage1_health import Stage1Health, describe


def statuses(*outcomes: bool) -> Stage1Health:
    health = Stage1Health()
    for failed in outcomes:
        health.record(failed=failed, reason="429 quota exceeded" if failed else None)
    return health


def test_no_calls_yet_is_unknown_not_ok():
    """A fresh process has not proved anything works. Claiming 'ok' would be a lie."""
    status = Stage1Health().status()

    assert status.state == "unknown"
    assert describe(status) is None, "nothing has failed, so there is nothing to warn about"


def test_all_recent_calls_failing_is_down():
    status = statuses(True, True, True).status()

    assert status.state == "down"
    assert status.degraded
    assert status.last_failure == "429 quota exceeded"


def test_some_failures_is_degraded_not_down():
    status = statuses(False, True, False, False).status()

    assert status.state == "degraded"
    assert (status.recent_failures, status.recent_calls) == (1, 4)


def test_recovery_clears_the_warning():
    """A window of successes after a failure must return to ok, or the banner sticks."""
    health = Stage1Health(window=2)
    health.record(failed=True, reason="transport")
    health.record(failed=False)
    health.record(failed=False)

    assert health.status().state == "ok"
    assert describe(health.status()) is None


def test_the_message_names_the_likely_cause_and_the_consequence():
    """A warning that does not say what to do about it does not prevent the failure."""
    message = describe(statuses(True, True).status())

    assert message is not None
    assert "quota" in message.lower(), "the operator needs the likely cause"
    assert "worse" in message.lower(), "and the consequence, or they will ignore it"
    assert "429 quota exceeded" in message, "and the actual error"


@pytest.fixture
def failing_stage1(app):
    """Every stage 1 call fails, exactly as it does when the daily quota is gone."""
    broken = FakeStageOne(fails="429 RESOURCE_EXHAUSTED: quota exceeded")
    app.dependency_overrides[search_router.get_query_understanding] = lambda: broken
    return broken


async def test_search_still_answers_when_stage1_is_down(api, doubles, failing_stage1):
    """Degrading beats 500ing. The point is that it degrades *visibly*."""
    doubles["ocr"].text = "government of india aadhaar identity"
    await api.post("/uploads", files={"file": ("id.png", make_png(), "image/png")})

    response = await api.post("/search", json={"query": "aadhaar identity card"})

    assert response.status_code == 200
    assert response.json()["results"], "the fallback must still retrieve"


async def test_the_response_says_stage1_failed_and_why(api, doubles, failing_stage1):
    doubles["ocr"].text = "government of india aadhaar identity"
    await api.post("/uploads", files={"file": ("id.png", make_png(), "image/png")})

    body = (await api.post("/search", json={"query": "aadhaar identity card"})).json()

    assert body["stage1_failed"] is True
    assert "quota" in body["stage1_failure_reason"].lower()
    assert body["degraded_message"], "a flag no UI renders is not a guard"
    assert "worse" in body["degraded_message"].lower()


async def test_a_working_stage1_carries_no_warning(api, doubles):
    doubles["ocr"].text = "government of india aadhaar identity"
    await api.post("/uploads", files={"file": ("id.png", make_png(), "image/png")})

    body = (await api.post("/search", json={"query": "aadhaar identity card"})).json()

    assert body["stage1_failed"] is False
    assert body["degraded_message"] is None, "a warning that is always on gets ignored"


async def test_deliberately_disabling_stage1_is_not_a_failure(api, doubles):
    """The ablation arm runs dense-only on purpose. That is a choice, not a fault."""
    doubles["ocr"].text = "government of india aadhaar identity"
    await api.post("/uploads", files={"file": ("id.png", make_png(), "image/png")})

    body = (
        await api.post("/search", json={"query": "aadhaar identity", "stage1": False})
    ).json()

    assert body["stage1_failed"] is False
    assert body["degraded_message"] is None


async def test_readiness_reports_stage1_before_anyone_searches(api, doubles, failing_stage1):
    """The pre-flight instrument: check this before the demo, not during it."""
    assert (await api.get("/health/ready")).json()["query_understanding"] == "unknown"

    doubles["ocr"].text = "government of india aadhaar"
    await api.post("/uploads", files={"file": ("id.png", make_png(), "image/png")})
    await api.post("/search", json={"query": "aadhaar"})

    ready = (await api.get("/health/ready")).json()
    assert ready["query_understanding"] == "down"
    assert ready["status"] == "degraded", "a degraded search path is not a ready system"
    assert "quota" in ready["degraded_message"].lower()

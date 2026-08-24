"""Skipping stage 1 when the query has nothing to extract.

Stage 1 costs one of twenty daily generate calls. When a query names no source type, no
sender and no date, stage 1 returns an empty extraction — the call buys nothing.

The asymmetry is the whole design: a wrong skip loses a filter the query needed, a wrong
run costs one call. So these tests are weighted toward proving the heuristic does *not*
skip things it should run.
"""

import pytest
from support import FakeStageOne, make_png

from memora.api.routers import search as search_router
from memora.services.query_signal import has_filterable_signal, why

RUN = [
    pytest.param("that motivation photo with the quote", "source type", id="photo"),
    pytest.param("the screenshot of that dashboard", "source type", id="screenshot"),
    pytest.param("the mail yash sent to rutuja", "source type + sender", id="mail"),
    pytest.param("the whatsapp message from aradhana", "source type + sender", id="chat"),
    pytest.param("the ai job someone forwarded to me", "sender verb", id="forwarded"),
    pytest.param("the job thing anu priya sent", "sender verb", id="name-sent"),
    pytest.param("the youtube course link in my calendar", "source type", id="calendar"),
    pytest.param("where are my birthday reminders kept", "source type", id="reminders"),
    pytest.param("what i had planned to learn last year", "relative date", id="last-year"),
    pytest.param("when was i supposed to fill the form", "date word", id="when"),
    pytest.param("the notes i wrote in march", "month", id="month"),
    pytest.param("what happened in 2024", "year", id="year"),
]

SKIP = [
    pytest.param("the project report about ai agents that write code", id="q002"),
    pytest.param("the synopsis about checking code for mistakes", id="q003"),
    pytest.param("the project about making websites do things on their own", id="q004"),
    pytest.param("the uipath job in chennai", id="q011"),
    pytest.param("my passport", id="q020"),
    pytest.param("my college fee receipt", id="q021"),
]


@pytest.mark.parametrize("query,signal", RUN)
def test_runs_when_the_query_names_something_filterable(query: str, signal: str):
    assert has_filterable_signal(query), f"{signal} missed in: {query}"


@pytest.mark.parametrize("query", SKIP)
def test_skips_when_there_is_nothing_to_extract(query: str):
    assert not has_filterable_signal(query), f"unnecessary call: {why(query)}"


def test_common_prepositions_alone_do_not_count_as_a_sender():
    """The trap this design nearly fell into.

    A bare word list containing "to", "by", "last" or "this" matches almost every English
    sentence. The heuristic would skip nothing while appearing to work — and the only
    symptom would be a quota that still runs out.
    """
    assert not has_filterable_signal("the list of drone topics i was supposed to learn")
    assert not has_filterable_signal("the thing i wanted to build by myself")
    assert not has_filterable_signal("that uber clone thing i planned to build")


def test_last_needs_a_period_to_be_a_date():
    assert not has_filterable_signal("the last thing i worked on")
    assert has_filterable_signal("the thing i worked on last month")


def test_why_explains_the_decision():
    """A skip that cannot be inspected is a skip that gets trusted by default."""
    assert "photo" in why("that motivation photo")
    assert why("my passport") == "no source-type, sender or date word"


def test_case_and_punctuation_do_not_change_the_decision():
    assert has_filterable_signal("The SCREENSHOT, of that dashboard!")
    assert has_filterable_signal("Photo?")


async def test_a_skipped_search_makes_no_stage1_call(api, doubles, app):
    """The point of the whole exercise: the call is not made."""
    spy = FakeStageOne()
    app.dependency_overrides[search_router.get_query_understanding] = lambda: spy
    doubles["ocr"].text = "uipath chennai job opening"
    await api.post("/uploads", files={"file": ("job.png", make_png(), "image/png")})

    body = (await api.post("/search", json={"query": "the uipath job in chennai"})).json()

    assert spy.calls == [], "stage 1 was called for a query with no filterable signal"
    assert body["stage1_skipped"] is True
    assert body["stage1_skip_reason"]
    assert body["results"], "skipping stage 1 must not stop retrieval"


async def test_a_skip_is_not_reported_as_a_failure(api, doubles):
    """A skip is a choice; a failure is a fault.

    If a skip set stage1_failed, a real quota outage could hide inside a field that looks
    deliberate — which is exactly the silent degradation the guard exists to prevent.
    """
    doubles["ocr"].text = "uipath chennai job opening"
    await api.post("/uploads", files={"file": ("job.png", make_png(), "image/png")})

    body = (await api.post("/search", json={"query": "my passport"})).json()

    assert body["stage1_skipped"] is True
    assert body["stage1_failed"] is False
    assert body["stage1_failure_reason"] is None
    assert body["degraded_message"] is None, "a skip is not a degradation"


async def test_a_signalled_query_still_calls_stage1(api, doubles, app):
    spy = FakeStageOne(source_types=["image"])
    app.dependency_overrides[search_router.get_query_understanding] = lambda: spy
    doubles["ocr"].text = "dashboard with forms"
    await api.post("/uploads", files={"file": ("d.png", make_png(), "image/png")})

    body = (await api.post("/search", json={"query": "the screenshot of a dashboard"})).json()

    assert spy.calls == ["the screenshot of a dashboard"]
    assert body["stage1_skipped"] is False


async def test_disabling_stage1_does_not_report_a_skip(api, doubles):
    """The ablation arm turns stage 1 off wholesale. That is not the heuristic skipping."""
    doubles["ocr"].text = "uipath chennai job"
    await api.post("/uploads", files={"file": ("job.png", make_png(), "image/png")})

    body = (
        await api.post("/search", json={"query": "my passport", "stage1": False})
    ).json()

    assert body["stage1_skipped"] is False

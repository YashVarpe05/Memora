"""Which config source won, reported rather than assumed.

The failure this exists to prevent has already happened. A key written into `.env` sat
inert while a different one from a Windows user variable did the work, with no symptom.

For a credential that is confusing. For `gemini_model` it is dangerous: the pin exists to
stop silent model substitution, after `gemini-flash-lite-latest` was swapped in to dodge a
quota limit and dropped Recall@1 to 0.789 — *below* the 0.842 achieved by using no
extractor at all. A pin overridden by a shell variable produces exactly the contamination
the pin prevents, and every report would still say the model was pinned.
"""

import pytest

from memora.config_provenance import SECRET, WATCHED, describe, report


class FakeSettings:
    gemini_api_key = "AIzaSyEXAMPLEEXAMPLEEXAMPLEEXAMPLE12345"
    gemini_model = "gemini-2.5-flash"
    database_url = "postgresql+asyncpg://memora_app:memora_app@localhost:5433/memora"
    stage1_cache = False


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    """A .env in cwd, so provenance reads a real file rather than a mock."""
    monkeypatch.chdir(tmp_path)
    return tmp_path / ".env"


def origins_by_field(settings=None):
    return {o.field: o for o in describe(settings or FakeSettings())}


def test_a_shell_variable_shadowing_env_is_flagged(env_file, monkeypatch):
    """The exact 2026-08-26 failure: .env says one thing and is silently losing."""
    env_file.write_text("GEMINI_API_KEY=from-the-file\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "from-the-shell")

    origin = origins_by_field()["gemini_api_key"]

    assert origin.source == "shell environment"
    assert origin.shadowed is True, "a losing .env value must be called out, not just ranked"
    assert "IGNORED" in "\n".join(report(FakeSettings()))


def test_env_alone_is_not_flagged_as_shadowed(env_file, monkeypatch):
    """No conflict, no warning. A warning that is always on is one nobody reads."""
    env_file.write_text("GEMINI_API_KEY=from-the-file\n", encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    origin = origins_by_field()["gemini_api_key"]

    assert origin.source == ".env"
    assert origin.shadowed is False
    assert "IGNORED" not in "\n".join(report(FakeSettings()))


def test_a_pinned_model_overridden_by_a_shell_variable_is_visible(env_file, monkeypatch):
    """The dangerous case, and the reason this module covers more than credentials."""
    env_file.write_text("GEMINI_MODEL=gemini-2.5-flash\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-flash-lite-latest")

    origin = origins_by_field()["gemini_model"]

    assert origin.shadowed is True, (
        "a model pin silently overridden reintroduces the contamination PHASE3.md "
        "measured at Recall@1 0.789, below using no extractor at all"
    )


def test_the_default_is_named_as_a_default(env_file, monkeypatch):
    env_file.write_text("", encoding="utf-8")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    assert origins_by_field()["gemini_model"].source == "default"


def test_secrets_are_masked_but_still_distinguishable(env_file, monkeypatch):
    """Two different keys were in play. Prefix and length tell them apart; neither is usable."""
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    line = origins_by_field()["gemini_api_key"].display

    assert FakeSettings.gemini_api_key not in line, "the key itself must never be printed"
    assert line.startswith("AIzaSy")
    assert "39 chars" in line


def test_non_secrets_are_shown_in_full(env_file):
    """A database URL that is wrong is only obvious if it can be read."""
    assert "localhost:5433" in origins_by_field()["database_url"].display


def test_an_empty_env_value_does_not_count_as_set(env_file, monkeypatch):
    """`.env.example` ships `GEMINI_API_KEY=` with no value. That is not a source."""
    env_file.write_text("GEMINI_API_KEY=\n", encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    assert origins_by_field()["gemini_api_key"].source == "default"


def test_every_watched_field_is_reported(env_file):
    assert set(origins_by_field()) == set(WATCHED)


def test_the_api_key_is_treated_as_a_secret():
    assert "gemini_api_key" in SECRET


def test_report_is_ascii_only(env_file, monkeypatch):
    """It goes to a Windows console. A non-cp1252 byte makes grep call the stream binary
    and hide the line, which is the opposite of making it visible."""
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    text = "\n".join(report(FakeSettings()))

    text.encode("ascii")  # raises if not

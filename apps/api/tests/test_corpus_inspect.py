"""Corpus inspector. The contract that matters: it never writes a query."""

import json

from memora.eval.inspect import (
    FileInfo,
    ascii_safe,
    classify,
    inspect_corpus,
    write_draft,
)

from support import make_pdf


def test_classify_by_suffix(tmp_path):
    cases = {
        "a.pdf": "pdf",
        "b.JPEG": "image",
        "c.m4a": "audio",
        "d.eml": "text",
        "e.xyz": "unknown",
    }
    for name, expected in cases.items():
        assert classify(tmp_path / name) == expected


def test_pdf_preview_is_extracted(tmp_path):
    (tmp_path / "notes.pdf").write_bytes(make_pdf(["Normalization removes redundancy."]))

    rows = inspect_corpus(tmp_path)

    assert len(rows) == 1
    assert rows[0].kind == "pdf"
    assert "Normalization" in rows[0].preview


def test_unreadable_file_is_reported_not_fatal(tmp_path):
    (tmp_path / "good.pdf").write_bytes(make_pdf(["fine"]))
    (tmp_path / "broken.pdf").write_bytes(b"%PDF-1.4 truncated garbage")

    rows = inspect_corpus(tmp_path)

    assert len(rows) == 2, "one bad file must not stop the listing"
    broken = next(r for r in rows if r.name == "broken.pdf")
    assert broken.error is not None
    assert broken.preview == "(unreadable)"


def test_dotfiles_are_skipped(tmp_path):
    (tmp_path / ".gitkeep").write_text("", encoding="utf-8")
    (tmp_path / "real.txt").write_text("hello", encoding="utf-8")

    assert [r.name for r in inspect_corpus(tmp_path)] == ["real.txt"]


def test_draft_never_contains_a_query(tmp_path):
    """The whole point. A gold query cannot be derived from file contents."""
    rows = [FileInfo(name="a.pdf", kind="pdf", size_bytes=1, preview="some text")]
    out = tmp_path / "GOLD.jsonl.draft"

    write_draft(rows, out)

    entries = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    queries = [e for e in entries if "query" in e]
    assert queries, "expected skeleton rows"
    assert all(e["query"] == "" for e in queries), "the tool must not invent queries"


def test_draft_carries_the_real_filename_and_a_refusal_row(tmp_path):
    rows = [FileInfo(name="mail.pdf", kind="pdf", size_bytes=1, preview="p")]
    out = tmp_path / "GOLD.jsonl.draft"

    write_draft(rows, out)
    entries = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]

    assert entries[1]["expected_sources"] == ["mail.pdf"]
    # must_refuse cites nothing, so it can never come from a file - but the gate
    # fails without one, so the skeleton is seeded.
    assert entries[-1]["type"] == "must_refuse"
    assert entries[-1]["expected_sources"] == []
    assert entries[-1]["query"] == ""


def test_empty_corpus_yields_nothing(tmp_path):
    assert inspect_corpus(tmp_path) == []


def test_ascii_fold_survives_a_cp1252_console():
    folded = ascii_safe("Academic Year 2026–27 — “quoted”")
    assert folded == 'Academic Year 2026-27 - "quoted"'
    folded.encode("cp1252")  # would raise if anything unencodable slipped through

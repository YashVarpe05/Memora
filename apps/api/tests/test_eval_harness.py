"""The eval harness must fail loudly while the gold set is still placeholders."""

import json
from pathlib import Path

from memora.eval.retrieval import check_corpus, load


def _write(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "GOLD.jsonl"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_comment_rows_are_skipped(tmp_path):
    gold = _write(
        tmp_path,
        '{"_comment": "delete me"}',
        '{"id": "q1", "query": "hi", "type": "content_semantic"}',
    )
    rows, errors = load(gold)
    assert len(rows) == 1
    assert errors == []


def test_duplicate_ids_are_reported(tmp_path):
    gold = _write(
        tmp_path,
        '{"id": "q1", "query": "a", "type": "content_semantic"}',
        '{"id": "q1", "query": "b", "type": "content_semantic"}',
    )
    _, errors = load(gold)
    assert any("duplicate id" in e for e in errors)


def test_unknown_type_is_reported(tmp_path):
    gold = _write(tmp_path, '{"id": "q1", "query": "a", "type": "vibes"}')
    _, errors = load(gold)
    assert any("unknown type" in e for e in errors)


def test_missing_corpus_file_is_reported(tmp_path):
    gold = _write(
        tmp_path,
        '{"id": "q1", "query": "a", "type": "content_semantic", "expected_sources": ["nope.pdf"]}',
    )
    rows, _ = load(gold)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    missing = check_corpus(rows, corpus)
    assert missing == {"q1": ["nope.pdf"]}


def test_present_corpus_file_passes(tmp_path):
    gold = _write(
        tmp_path,
        '{"id": "q1", "query": "a", "type": "content_semantic", "expected_sources": ["real.pdf"]}',
    )
    rows, _ = load(gold)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "real.pdf").write_bytes(b"%PDF-1.4")
    assert check_corpus(rows, corpus) == {}


def test_full_type_coverage_is_required_to_pass(tmp_path):
    """20 well-formed rows still fail if a query type is absent.

    The harness printed type counts but never gated on them, so a set with no
    must_refuse row passed - and refusal is one of the two types the results
    table actually turns on.
    """
    from memora.eval.retrieval import KNOWN_TYPES, Report

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    partial = sorted(KNOWN_TYPES - {"must_refuse"})
    lines = []
    for i in range(20):
        name = f"f{i:02d}.pdf"
        (corpus / name).write_bytes(b"%PDF-1.4")
        lines.append(
            json.dumps(
                {
                    "id": f"q{i:03d}",
                    "query": "q",
                    "type": partial[i % len(partial)],
                    "expected_sources": [name],
                }
            )
        )
    gold = _write(tmp_path, *lines)

    rows, errors = load(gold)
    report = Report(rows=rows, schema_errors=errors, missing_sources=check_corpus(rows, corpus))

    assert report.missing_types == ["must_refuse"]
    assert not report.ok

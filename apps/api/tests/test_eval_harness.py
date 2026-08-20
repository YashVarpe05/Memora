"""The eval harness must fail loudly while the gold set is still placeholders."""

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
        '{"id": "q1", "query": "hi", "type": "semantic"}',
    )
    rows, errors = load(gold)
    assert len(rows) == 1
    assert errors == []


def test_duplicate_ids_are_reported(tmp_path):
    gold = _write(
        tmp_path,
        '{"id": "q1", "query": "a", "type": "semantic"}',
        '{"id": "q1", "query": "b", "type": "semantic"}',
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
        '{"id": "q1", "query": "a", "type": "semantic", "expected_sources": ["nope.pdf"]}',
    )
    rows, _ = load(gold)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    missing = check_corpus(rows, corpus)
    assert missing == {"q1": ["nope.pdf"]}


def test_present_corpus_file_passes(tmp_path):
    gold = _write(
        tmp_path,
        '{"id": "q1", "query": "a", "type": "semantic", "expected_sources": ["real.pdf"]}',
    )
    rows, _ = load(gold)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "real.pdf").write_bytes(b"%PDF-1.4")
    assert check_corpus(rows, corpus) == {}

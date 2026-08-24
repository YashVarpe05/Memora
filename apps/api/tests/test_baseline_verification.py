"""The eval must refuse to report a number describing a corpus that is not there.

Ingest and evaluation are separated so a measurement costs 21 embeds rather than 421.
The cost of that separation is that the index can drift from the disk, and a drifted
index produces a plausible number for the wrong corpus - which is worse than an error,
because nobody checks a green result.
"""

from memora.eval.baseline import corpus_hashes, verify_corpus
from memora.eval.retrieval import GoldRow

from support import make_pdf


def row(name: str) -> GoldRow:
    return GoldRow(id="q1", query="x", type="content_semantic", expected_sources=[name])


def test_matching_index_has_no_problems():
    on_disk = {"aaa": "one.pdf", "bbb": "two.pdf"}
    indexed = {"aaa": "one.pdf", "bbb": "two.pdf"}

    assert verify_corpus(on_disk, indexed, [row("one.pdf")]) == []


def test_a_file_on_disk_that_was_never_indexed_is_not_an_error():
    """Several corpus files are rejected at upload for having no extractable text.

    That is expected and already recorded as a finding, so it must not fail the run.
    """
    on_disk = {"aaa": "one.pdf", "ccc": "blank.png"}
    indexed = {"aaa": "one.pdf"}

    assert verify_corpus(on_disk, indexed, [row("one.pdf")]) == []


def test_an_indexed_document_missing_from_disk_is_reported():
    """Deleted or edited since ingest - the index describes a corpus that is gone."""
    on_disk = {"aaa": "one.pdf"}
    indexed = {"aaa": "one.pdf", "old": "deleted.pdf"}

    problems = verify_corpus(on_disk, indexed, [row("one.pdf")])

    assert len(problems) == 1
    assert "deleted.pdf" in problems[0]


def test_an_edited_file_is_reported_because_its_hash_changed():
    on_disk = {"NEWHASH": "one.pdf"}
    indexed = {"OLDHASH": "one.pdf"}

    problems = verify_corpus(on_disk, indexed, [row("one.pdf")])

    assert any("one.pdf" in p for p in problems)


def test_a_gold_row_whose_file_is_not_indexed_is_reported():
    """Otherwise the row fails and the failure is charged to retrieval.

    The cause would be a missing document, and the number would be wrong in the
    direction that makes the system look worse than it is.
    """
    on_disk = {"aaa": "one.pdf", "bbb": "two.pdf"}
    indexed = {"aaa": "one.pdf"}

    problems = verify_corpus(on_disk, indexed, [row("one.pdf"), row("two.pdf")])

    assert len(problems) == 1
    assert "two.pdf" in problems[0]
    assert "not indexed" in problems[0]


def test_refusal_rows_expect_no_file_and_never_trigger_a_problem():
    refusal = GoldRow(id="q20", query="my passport", type="must_refuse", expected_sources=[])

    assert verify_corpus({"aaa": "one.pdf"}, {"aaa": "one.pdf"}, [refusal]) == []


def test_corpus_hashes_reads_real_files(tmp_path):
    (tmp_path / "a.pdf").write_bytes(make_pdf(["hello"]))
    (tmp_path / ".gitkeep").write_text("", encoding="utf-8")

    hashes = corpus_hashes(tmp_path)

    assert list(hashes.values()) == ["a.pdf"], "dotfiles must be skipped"
    assert len(next(iter(hashes))) == 64


def test_identical_content_under_two_names_collapses_to_one_hash(tmp_path):
    """Content addressing means a duplicate is one entry, which is correct - the
    index deduplicates it too."""
    data = make_pdf(["same"])
    (tmp_path / "a.pdf").write_bytes(data)
    (tmp_path / "b.pdf").write_bytes(data)

    assert len(corpus_hashes(tmp_path)) == 1

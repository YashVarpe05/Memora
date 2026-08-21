"""OCR benchmark harness.

Engines are faked so the pipeline is deterministic and the suite never depends on
paddle, a tesseract binary, or a metered API call.
"""

from pathlib import Path

from memora.bench.engines import Availability, OcrEngine
from memora.bench.ocr import MIN_IMAGES, REQUIRED_CATEGORIES, Corpus, discover, measure, normalize


class FakeEngine(OcrEngine):
    """Returns a canned transcript, or raises, per image stem."""

    name = "fake"

    def __init__(self, outputs: dict[str, str | Exception]) -> None:
        self._outputs = outputs

    def availability(self) -> Availability:
        return Availability(True, "ready")

    def read(self, image: Path) -> str:
        out = self._outputs[image.stem]
        if isinstance(out, Exception):
            raise out
        return out


def build(tmp_path: Path, spec: dict[str, tuple[str, str | None]]) -> tuple[Path, Path]:
    """spec: {"category/stem": (reference_text | None)} -> image and refs roots."""
    images, refs = tmp_path / "images", tmp_path / "refs"
    for key, (suffix, reference) in spec.items():
        category, stem = key.split("/")
        image = images / category / f"{stem}{suffix}"
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"\x89PNG")
        if reference is not None:
            ref = refs / category / f"{stem}.txt"
            ref.parent.mkdir(parents=True, exist_ok=True)
            ref.write_text(reference, encoding="utf-8")
    return images, refs


def test_discover_pairs_images_with_references(tmp_path):
    images, refs = build(tmp_path, {"printed/page1": (".png", "hello world")})
    corpus = discover(images, refs)

    assert len(corpus.samples) == 1
    sample = corpus.samples[0]
    assert sample.category == "printed"
    assert sample.stem == "page1"
    assert sample.reference is not None
    assert corpus.missing_refs == []


def test_image_without_a_reference_is_reported(tmp_path):
    images, refs = build(tmp_path, {"whiteboard/board": (".jpg", None)})
    corpus = discover(images, refs)

    assert corpus.missing_refs == [str(Path("whiteboard") / "board.txt")]
    assert not corpus.ok


def test_non_image_files_are_ignored(tmp_path):
    images, refs = build(tmp_path, {"printed/page1": (".png", "x")})
    (images / "printed" / "notes.txt").write_text("not an image", encoding="utf-8")

    assert len(discover(images, refs).samples) == 1


def test_missing_category_blocks_readiness(tmp_path):
    spec = {}
    for i in range(MIN_IMAGES):
        category = sorted(REQUIRED_CATEGORIES - {"handwritten"})[i % 4]
        spec[f"{category}/img{i}"] = (".png", "text")
    images, refs = build(tmp_path, spec)
    corpus = discover(images, refs)

    assert corpus.missing_categories == ["handwritten"]
    assert not corpus.ok


def test_complete_corpus_is_ready(tmp_path):
    """The green path - the branch that sits unexecuted until it matters."""
    spec = {}
    for i in range(MIN_IMAGES):
        category = sorted(REQUIRED_CATEGORIES)[i % len(REQUIRED_CATEGORIES)]
        spec[f"{category}/img{i}"] = (".png", "text")
    images, refs = build(tmp_path, spec)
    corpus = discover(images, refs)

    assert corpus.missing_categories == []
    assert corpus.missing_refs == []
    assert len(corpus.samples) == MIN_IMAGES
    assert corpus.ok


def test_normalize_collapses_whitespace_and_case():
    assert normalize("  Hello   \n World ", lowercase=True) == "hello world"
    assert normalize("  Hello   \n World ", lowercase=False) == "Hello World"


def test_perfect_read_scores_zero_cer(tmp_path):
    images, refs = build(tmp_path, {"printed/page1": (".png", "the quick brown fox")})
    corpus = discover(images, refs)

    rows = measure(FakeEngine({"page1": "The Quick  Brown Fox"}), corpus.samples, lowercase=True)

    assert len(rows) == 1
    assert rows[0].cer == 0.0
    assert rows[0].error is None


def test_wrong_read_scores_nonzero_cer(tmp_path):
    images, refs = build(tmp_path, {"printed/page1": (".png", "the quick brown fox")})
    corpus = discover(images, refs)

    rows = measure(FakeEngine({"page1": "xxxxx"}), corpus.samples, lowercase=True)

    assert rows[0].cer is not None
    assert rows[0].cer > 0.5


def test_case_sensitivity_changes_the_score(tmp_path):
    """Normalization materially moves CER, which is why the run reports it."""
    images, refs = build(tmp_path, {"printed/page1": (".png", "Hello World")})
    corpus = discover(images, refs)
    engine = FakeEngine({"page1": "hello world"})

    assert measure(engine, corpus.samples, lowercase=True)[0].cer == 0.0
    assert measure(engine, corpus.samples, lowercase=False)[0].cer > 0.0


def test_one_failing_image_does_not_end_the_run(tmp_path):
    images, refs = build(
        tmp_path,
        {"printed/good": (".png", "hello"), "printed/bad": (".png", "world")},
    )
    corpus = discover(images, refs)
    engine = FakeEngine({"good": "hello", "bad": RuntimeError("decode failed")})

    rows = measure(engine, corpus.samples, lowercase=True)

    assert len(rows) == 2
    failed = next(r for r in rows if r.stem == "bad")
    assert failed.cer is None
    assert failed.error is not None
    assert "decode failed" in failed.error


def test_samples_without_references_are_not_measured(tmp_path):
    images, refs = build(tmp_path, {"printed/a": (".png", "x"), "printed/b": (".png", None)})
    corpus = discover(images, refs)

    rows = measure(FakeEngine({"a": "x"}), corpus.samples, lowercase=True)

    assert [r.stem for r in rows] == ["a"]


def test_empty_corpus_is_not_ready():
    assert not Corpus().ok

"""The phone's copy of the document-type rules must match the server's."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "export_document_types.py"


def _module():
    spec = importlib.util.spec_from_file_location("memora_export_types", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_checked_in_vocabulary_matches_the_python_rules():
    module = _module()
    assert module.TARGET.read_text(encoding="utf-8") == module.render(), (
        "Run: python3 scripts/export_document_types.py"
    )


def test_every_type_and_stop_word_is_exported():
    module = _module()
    text = module.render()
    from memora.services.document_type import VOCABULARY
    from memora.services.lexical import STOP

    for label in VOCABULARY:
        assert f"\nT\t{label}\t" in text
    assert text.count("\nS\t") == len(STOP)

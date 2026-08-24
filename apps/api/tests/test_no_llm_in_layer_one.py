"""No document content in any prompt, at layer one. Enforced structurally.

PRODUCT.md architectural rule 1 draws the line at **what goes into the prompt**, not at
whether a model is called. Stage 1 sends the user's own query and is permitted. Anything
carrying chunk text, filenames, snippets or results is forbidden, however much it might
improve the ranking.

Two checks, because the rule has two halves:

- layer one must not import the generation module, which takes chunks by construction
- the stage 1 prompt builder must accept a query string and nothing else, so there is no
  parameter through which a document could arrive

A behaviour test - "no generator was called" - passes right up until someone adds the
forbidden step. Same instinct as require_masked: check the structure, not the symptom.
"""

import ast
from pathlib import Path

import pytest

LAYER_ONE = (
    "memora/services/search.py",
    "memora/api/routers/search.py",
    "memora/services/query_understanding.py",
)

# The generation module takes chunks. Reaching it from layer one is the violation.
# `google.genai` is NOT forbidden any more: stage 1 is a permitted model call, and
# banning the SDK would ban the permitted half along with the forbidden one.
FORBIDDEN = ("generation",)

SRC = Path(__file__).resolve().parents[1] / "src"


def imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


@pytest.mark.parametrize("relative", LAYER_ONE)
def test_layer_one_cannot_reach_generation(relative):
    imports = imported_names(SRC / relative)

    offenders = [
        name
        for name in imports
        for banned in FORBIDDEN
        if name == banned or name.endswith(f".{banned}")
    ]

    assert not offenders, (
        f"{relative} imports {offenders}. Layer one must return files without a "
        "generation call - see PRODUCT.md architectural rule 1."
    )


def test_the_guard_would_catch_a_violation(tmp_path):
    """A guard nobody has seen fail is a guard nobody knows works."""
    offending = tmp_path / "bad.py"
    offending.write_text(
        "from memora.services.generation import build_generator\n", encoding="utf-8"
    )

    imports = imported_names(offending)

    assert any(name.endswith(".generation") for name in imports)


def test_stage_one_prompt_accepts_a_query_and_nothing_else():
    """The signature is the enforcement.

    build_prompt takes a query string. There is no parameter through which a chunk, a
    filename, a snippet or a result could be passed, so the forbidden prompt cannot be
    constructed without changing this signature - which fails this test.
    """
    import inspect

    from memora.services.query_understanding import build_prompt

    parameters = inspect.signature(build_prompt).parameters
    assert list(parameters) == ["query", "today"]
    assert parameters["query"].annotation == "str"


def test_stage_one_prompt_contains_only_the_query():
    from memora.services.query_understanding import build_prompt

    prompt = build_prompt("the mail yash sent to rutuja")

    assert "the mail yash sent to rutuja" in prompt
    for leaked in ("chunk", "snippet", ".pdf", ".jpeg", "GOVERNMENT OF INDIA"):
        assert leaked not in prompt


def test_stage_one_does_not_import_retrieval_types():
    """It cannot be handed a result even by accident."""
    imports = imported_names(SRC / "memora/services/query_understanding.py")

    for banned in ("memora.repositories.chunk", "memora.services.search"):
        assert not any(name.startswith(banned) for name in imports), (
            f"query_understanding imports {banned}; it must never see a retrieval result."
        )

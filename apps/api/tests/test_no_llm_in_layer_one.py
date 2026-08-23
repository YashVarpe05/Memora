"""Layer one runs without an LLM. Enforced on the import graph.

PRODUCT.md architectural rule 1 says finding a file never sends any part of it to a
model. A behaviour test - "no generator was called" - passes right up until someone adds
a summarise-the-results step, at which point the rule is gone and the suite is still
green. Checking what the module can even reach catches that at the moment it is written.

Same instinct as require_masked: check the structure, not the symptom.
"""

import ast
from pathlib import Path

import pytest

LAYER_ONE = ("memora/services/search.py", "memora/api/routers/search.py")

FORBIDDEN = ("generation", "google.genai", "genai")

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

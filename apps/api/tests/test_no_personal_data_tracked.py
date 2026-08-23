"""No personal document may be tracked by git.

This has happened twice. Both times the ignore rule was root-anchored while the command
ran from apps/api, so the files landed one directory deeper than the pattern reached -
first the corpus, then the blob store, which put 15 real documents and a four-year
calendar export into two commits.

Both times it was caught by someone noticing. This makes the third time a failing test.

It checks what git actually tracks rather than what .gitignore says, because the bug was
never in the intent - it was in the gap between the intent and the anchoring.
"""

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]

# Directory names that only ever hold personal documents, at any depth.
PERSONAL_DIRS = ("data/corpus/", "data/blobs/", "data/samples/", "data/ocr-bench/")

# Files that carry extracted content from those documents.
PERSONAL_FILES = ("GOLD.jsonl.draft",)

KEEP = (".gitkeep",)


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("not a git repository")
    return result.stdout.splitlines()


def offenders(paths: list[str]) -> list[str]:
    found = []
    for path in paths:
        if Path(path).name in KEEP:
            continue
        normalised = path.replace("\\", "/")
        in_personal_dir = any(marker in normalised for marker in PERSONAL_DIRS)
        is_personal_file = any(normalised.endswith(name) for name in PERSONAL_FILES)
        if in_personal_dir or is_personal_file:
            found.append(path)
    return found


def test_no_personal_document_is_tracked():
    found = offenders(tracked_files())

    assert not found, (
        f"{len(found)} personal file(s) are tracked by git, e.g. {found[:3]}. "
        "Remove them from the index AND from history - an ignore rule added afterwards "
        "does not remove what is already committed."
    )


def test_no_personal_document_is_in_any_commit():
    """The index being clean is not enough. History is what gets pushed."""
    result = subprocess.run(
        ["git", "log", "--all", "--pretty=format:%h", "--name-only"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("not a git repository")

    found = offenders([line for line in result.stdout.splitlines() if "/" in line])

    assert not found, (
        f"{len(found)} personal file path(s) appear in history, e.g. {found[:3]}. "
        "An ignore rule does not rewrite history."
    )


@pytest.mark.parametrize(
    "path",
    [
        "data/blobs/user/abc",
        "apps/api/data/blobs/user/abc",
        "apps/web/data/blobs/user/abc",
        "data/corpus/private.pdf",
        "apps/api/data/corpus/private.pdf",
        "data/samples/third-party.pdf",
        "apps/api/data/samples/third-party.pdf",
        "docs/GOLD.jsonl.draft",
        "apps/api/docs/GOLD.jsonl.draft",
    ],
)
def test_ignore_rules_work_from_any_depth(path):
    """The actual defect, twice over: a rule that only works from the repo root.

    check-ignore is asked directly, so this fails if someone re-anchors a pattern.
    """
    result = subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"'{path}' is NOT ignored. A pattern containing a slash is anchored to the "
        ".gitignore's directory - prefix it with **/ so depth does not matter."
    )

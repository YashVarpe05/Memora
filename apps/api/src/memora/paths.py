"""Repo-root resolution, so commands work from any working directory."""

from pathlib import Path


def repo_root() -> Path:
    """Walk up to the directory holding CLAUDE.md."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "CLAUDE.md").exists():
            return parent
    return Path.cwd()


def resolve(path: Path) -> Path:
    """Resolve a path the user typed: as given, else relative to the repo root.

    Only for explicit arguments. Do NOT use for defaults - it prefers whatever exists
    relative to the current directory, so a stray `data/corpus` under apps/api silently
    wins over the real one. Use `anchored()` for defaults.
    """
    if path.exists() or path.is_absolute():
        return path
    return repo_root() / path


def anchored(relative: str) -> Path:
    """A project location, always the same one, whatever directory you are standing in.

    Two bugs came from the alternative: a second blob tree under apps/api holding real
    documents outside the ignore rule, and a decoy corpus that made the inspector report
    one file instead of fifteen.
    """
    return repo_root() / relative

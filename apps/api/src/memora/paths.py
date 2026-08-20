"""Repo-root resolution, so commands work from any working directory."""

from pathlib import Path


def repo_root() -> Path:
    """Walk up to the directory holding CLAUDE.md."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "CLAUDE.md").exists():
            return parent
    return Path.cwd()


def resolve(path: Path) -> Path:
    """Try the path as given, then relative to the repo root."""
    if path.exists() or path.is_absolute():
        return path
    return repo_root() / path

"""Dump the OpenAPI schema to a file.

CLAUDE.md: API types are GENERATED from OpenAPI, never hand-written. This is the
first half of `pnpm gen:types`.

It builds the app in-process, so type generation needs no running server — four
people can regenerate types offline, and CI can check the contract without booting
anything.

    uv run python -m memora.openapi           # writes <repo>/openapi.json
    uv run python -m memora.openapi -         # writes to stdout
"""

import json
import sys
from pathlib import Path

from memora.main import create_app
from memora.paths import repo_root


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    payload = json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"

    if args and args[0] == "-":
        sys.stdout.write(payload)
        return 0

    target = Path(args[0]) if args else repo_root() / "openapi.json"
    target.write_text(payload, encoding="utf-8")
    sys.stderr.write(f"wrote {target}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

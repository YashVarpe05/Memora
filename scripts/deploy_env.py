#!/usr/bin/env python3
"""Write .env.production for a Memora server, with fresh random secrets.

    python3 scripts/deploy_env.py memora.duckdns.org [--semantic] [--force]

Creates a file only the owner can read; refuses to overwrite one unless --force (rotating
secrets locks out every enrolled device that used the old ENROLLMENT_SECRET, and changing the
database passwords on an existing database breaks it). Prints the next commands.
"""

import argparse
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")


def render(domain: str, semantic: bool) -> str:
    lines = [
        f"MEMORA_DOMAIN={domain}",
        f"DB_PASSWORD={secrets.token_hex(16)}",
        f"APP_DB_PASSWORD={secrets.token_hex(16)}",
        f"OPERATOR_SECRET={secrets.token_urlsafe(32)}",
        f"ENROLLMENT_SECRET={secrets.token_urlsafe(32)}",
        f"WITH_SEMANTIC={'1' if semantic else '0'}",
        f"EMBEDDING_PROVIDER={'local' if semantic else 'lexical'}",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("domain")
    parser.add_argument(
        "--semantic",
        action="store_true",
        help="meaning-based search on the server (needs ~3 GB RAM)",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / ".env.production")
    args = parser.parse_args(argv)
    domain = args.domain.strip().lower()
    if not DOMAIN.match(domain):
        print(f"{domain!r} is not a domain name (example: memora.duckdns.org).", file=sys.stderr)
        return 2
    if args.out.exists() and not args.force:
        print(f"{args.out} exists. Keeping it; pass --force to replace it.", file=sys.stderr)
        return 1
    args.out.write_text(render(domain, args.semantic))
    args.out.chmod(0o600)
    secret = next(
        line.split("=", 1)[1]
        for line in args.out.read_text().splitlines()
        if line.startswith("ENROLLMENT_SECRET=")
    )
    print(f"Wrote {args.out} (readable only by you).")
    print("Next, on this server:")
    print("  docker compose -f compose.production.yml --env-file .env.production up -d --build")
    print("Then, on the computer that builds the phone app:")
    print(f"  scripts/build_apk.sh https://{domain}/api {secret}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Back up and restore-check a Memora server: database, stored files and device logins.

    python scripts/backup.py backup  [--production] [--out backups]
    python scripts/backup.py verify  BACKUP_DIR
    python scripts/backup.py restore-check BACKUP_DIR [--production]

A backup holds personal documents, so it is ENCRYPTED (AES-256, PBKDF2) with the passphrase
in MEMORA_BACKUP_PASSPHRASE and refuses to run without one unless --no-encrypt is given.
`restore-check` restores the database dump into a throwaway database, compares row counts
with the manifest, and drops it; it never touches the live database.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COUNTED = ("memories", "chunks", "index_jobs")


def compose(production: bool) -> list[str]:
    cmd = ["docker", "compose"]
    if production:
        cmd += ["-f", str(ROOT / "compose.production.yml")]
    return cmd


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def passphrase(no_encrypt: bool) -> str | None:
    if no_encrypt:
        return None
    value = os.environ.get("MEMORA_BACKUP_PASSPHRASE")
    if not value:
        sys.exit(
            "Set MEMORA_BACKUP_PASSPHRASE (backups hold personal documents), or pass --no-encrypt."
        )
    return value


def openssl(mode: str, source: Path, target: Path, secret: str) -> None:
    flag = "-e" if mode == "encrypt" else "-d"
    result = subprocess.run(
        [
            "openssl",
            "enc",
            flag,
            "-aes-256-cbc",
            "-pbkdf2",
            "-iter",
            "200000",
            "-in",
            str(source),
            "-out",
            str(target),
            "-pass",
            "env:MEMORA_BACKUP_PASSPHRASE",
        ],
        env={**os.environ, "MEMORA_BACKUP_PASSPHRASE": secret},
        capture_output=True,
        text=True,
    )
    if result.returncode:
        sys.exit(f"Could not {mode} {source.name}: wrong passphrase or a damaged file.")


def db_exec(production: bool, *args: str, stdin=None, capture=False):
    cmd = [*compose(production), "exec", "-T", "db", *args]
    return subprocess.run(
        cmd, cwd=ROOT, check=True, stdin=stdin, capture_output=capture, text=capture
    )


def counts(production: bool, database: str) -> dict[str, int]:
    out = {}
    for table in COUNTED:
        result = db_exec(
            production,
            "psql",
            "-U",
            "memora",
            "-d",
            database,
            "-At",
            "-c",
            f"select count(*) from {table}",
            capture=True,
        )
        out[table] = int(result.stdout.strip())
    return out


def state_paths(production: bool) -> list[tuple[str, Path]]:
    """Files outside the database: stored documents and the paired-device logins."""
    if production:
        return []  # copied out of the api container's /state volume instead
    return [("blobs", ROOT / "data/blobs"), ("auth", ROOT / "data/auth")]


def backup(args) -> Path:
    secret = passphrase(args.no_encrypt)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = Path(args.out) / stamp
    target.mkdir(parents=True)
    dump = target / "memora.dump"
    with dump.open("wb") as handle:
        subprocess.run(
            [
                *compose(args.production),
                "exec",
                "-T",
                "db",
                "pg_dump",
                "-U",
                "memora",
                "-Fc",
                "--no-owner",
                "memora",
            ],
            cwd=ROOT,
            check=True,
            stdout=handle,
        )
    archive = target / "state.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        if args.production:
            with tempfile.TemporaryDirectory() as scratch:
                subprocess.run(
                    [*compose(True), "cp", "api:/state/.", scratch], cwd=ROOT, check=True
                )
                tar.add(scratch, arcname="state")
        else:
            for name, path in state_paths(False):
                if path.exists():
                    tar.add(path, arcname=name)
    manifest = {
        "created": stamp,
        "production": args.production,
        "encrypted": secret is not None,
        "alembic_head": db_exec(
            args.production,
            "psql",
            "-U",
            "memora",
            "-d",
            "memora",
            "-At",
            "-c",
            "select version_num from alembic_version",
            capture=True,
        ).stdout.strip(),
        "counts": counts(args.production, "memora"),
        "files": {},
    }
    for path in (dump, archive):
        manifest["files"][path.name] = sha256(path)
        if secret:
            openssl("encrypt", path, path.with_name(path.name + ".enc"), secret)
            path.unlink()
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"backup written to {target}")
    return target


def verify(directory: Path, secret: str | None) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    with tempfile.TemporaryDirectory() as scratch:
        for name, expected in manifest["files"].items():
            source = directory / (name + (".enc" if manifest["encrypted"] else ""))
            if not source.exists():
                sys.exit(f"missing {source.name}")
            plain = source
            if manifest["encrypted"]:
                if not secret:
                    sys.exit("This backup is encrypted: set MEMORA_BACKUP_PASSPHRASE.")
                plain = Path(scratch) / name
                openssl("decrypt", source, plain, secret)
            if sha256(plain) != expected:
                sys.exit(
                    f"checksum mismatch for {name}: the backup is damaged"
                )
    print("backup verified: every file matches its checksum")
    return manifest


def restore_check(directory: Path, secret: str | None, production: bool) -> None:
    manifest = verify(directory, secret)
    scratch_db = "memora_restore_check"
    with tempfile.TemporaryDirectory() as scratch:
        source = directory / ("memora.dump" + (".enc" if manifest["encrypted"] else ""))
        dump = Path(scratch) / "memora.dump"
        if manifest["encrypted"]:
            openssl("decrypt", source, dump, secret or "")
        else:
            dump = source
        db_exec(
            production,
            "psql",
            "-U",
            "memora",
            "-d",
            "postgres",
            "-c",
            f"drop database if exists {scratch_db}",
        )
        db_exec(
            production,
            "psql",
            "-U",
            "memora",
            "-d",
            "postgres",
            "-c",
            f"create database {scratch_db}",
        )
        try:
            with dump.open("rb") as handle:
                db_exec(
                    production,
                    "pg_restore",
                    "-U",
                    "memora",
                    "-d",
                    scratch_db,
                    "--no-owner",
                    stdin=handle,
                )
            restored = counts(production, scratch_db)
        finally:
            db_exec(
                production,
                "psql",
                "-U",
                "memora",
                "-d",
                "postgres",
                "-c",
                f"drop database if exists {scratch_db}",
            )
    expected = manifest["counts"]
    if restored != expected:
        sys.exit(f"restore mismatch: backup had {expected}, restored {restored}")
    print(f"restore check passed: {restored} (scratch database dropped)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("backup", "verify", "restore-check"):
        p = sub.add_parser(name)
        if name == "backup":
            p.add_argument("--out", default=str(ROOT / "backups"))
        else:
            p.add_argument("directory", type=Path)
        p.add_argument("--production", action="store_true")
        p.add_argument("--no-encrypt", action="store_true")
    args = parser.parse_args()
    if args.command == "backup":
        backup(args)
        return
    secret = os.environ.get("MEMORA_BACKUP_PASSPHRASE")
    if args.command == "verify":
        verify(args.directory, secret)
    else:
        restore_check(args.directory, secret, args.production)


if __name__ == "__main__":
    main()

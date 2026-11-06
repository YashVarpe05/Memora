#!/usr/bin/env python3
"""Required local/CI gates. Missing services or skipped tests fail validation."""

import argparse
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "data/test-reports"


def run(args, cwd=ROOT, env=None):
    print("+ " + " ".join(args), flush=True)
    subprocess.run(args, cwd=cwd, env=env, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--e2e", action="store_true", help="Also run browser/OCR acceptance tests")
    parser.add_argument(
        "--audit", action="store_true", help="Audit production npm dependencies online"
    )
    parser.add_argument(
        "--semantic",
        action="store_true",
        help="Also require cached real-model semantic acceptance tests",
    )
    args = parser.parse_args()
    if args.semantic:
        os.environ["UV_NO_SYNC"] = "1"
    REPORTS.mkdir(parents=True, exist_ok=True)
    run(["docker", "compose", "up", "-d", "--wait", "db", "redis"])
    run(["uv", "run", "alembic", "upgrade", "head"], ROOT / "apps/api")
    run(["uv", "run", "ruff", "check", "."], ROOT / "apps/api")
    report = REPORTS / "api.xml"
    run(["uv", "run", "pytest", "-o", "addopts=", "-q", f"--junitxml={report}"], ROOT / "apps/api")
    suites = ET.parse(report).getroot().iter("testsuite")
    if any(int(suite.get("skipped", "0")) for suite in suites):
        raise SystemExit(
            "Validation failed: skipped API tests. Check database/service availability."
        )
    run(["pnpm", "--filter", "@memora/web", "test"])
    run(["pnpm", "typecheck"])
    run(["pnpm", "build"])
    generated = [ROOT / "openapi.json", ROOT / "packages/core/src/types/api.ts"]
    before = [path.read_bytes() for path in generated]
    run(["pnpm", "gen:types"])
    if before != [path.read_bytes() for path in generated]:
        raise SystemExit(
            "Generated API contract changed. Review generated files and rerun validation."
        )
    if args.audit:
        run(["pnpm", "audit", "--prod", "--audit-level", "high"])
    if args.e2e:
        for mode, lexical in [("hybrid-doubles", "0"), ("real-lexical", "1")]:
            env = {**os.environ, "MEMORA_E2E_LEXICAL": lexical}
            run(["pnpm", "--filter", "@memora/web", "test:e2e"], env=env)
            report_dir = ROOT / "apps/web/playwright-report"
            if report_dir.exists():
                shutil.copytree(report_dir, REPORTS / mode, dirs_exist_ok=True)
    if args.semantic:
        env = {**os.environ, "MEMORA_E2E_SEMANTIC": "1"}
        run(["pnpm", "--filter", "@memora/web", "test:e2e"], env=env)
        shutil.copytree(
            ROOT / "apps/web/playwright-report", REPORTS / "real-semantic", dirs_exist_ok=True
        )
    print("All selected validation gates passed. See data/test-reports for results.")


if __name__ == "__main__":
    main()

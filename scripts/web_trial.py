#!/usr/bin/env python3
"""Run a local, real OCR + keyword-search trial without cloud credentials."""

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--semantic",
        action="store_true",
        help="Enable local multilingual semantic search (model download required)",
    )
    args = parser.parse_args()
    for command in ("uv", "pnpm", "docker", "tesseract"):
        if not shutil.which(command):
            raise SystemExit(f"Missing {command}. Install it before starting the web trial.")
    env = os.environ.copy()
    env.update(
        ENVIRONMENT="development",
        EMBEDDING_PROVIDER="local" if args.semantic else "lexical",
        STAGE1_PROVIDER="rules",
        OCR_URL="http://127.0.0.1:8081",
        DATABASE_URL="postgresql+asyncpg://memora_app:memora_app@127.0.0.1:5433/memora",
        MIGRATION_DATABASE_URL="postgresql+asyncpg://memora:memora@127.0.0.1:5433/memora",
        REDIS_URL="redis://127.0.0.1:6379/0",
        GEMINI_API_KEY="",
        PUBLIC_API_URL="",
        OPERATOR_SECRET="",
        BLOB_ROOT=str(ROOT / "data/blobs/web-trial"),
        PAIRING_STORE=str(ROOT / "data/auth/web-trial.sqlite3"),
    )
    for port in (8000, 8081, 5175):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit(f"Port {port} is already in use; stop its existing service first.")
    languages = subprocess.check_output(["tesseract", "--list-langs"], env=env, text=True)
    required = env.get("OCR_LANGUAGES", "eng+hin+mar").split("+")
    missing = set(required) - set(languages.splitlines())
    if missing:
        raise SystemExit(
            "Missing Tesseract languages: "
            + ", ".join(sorted(missing))
            + ". Install their language packs or set TESSDATA_PREFIX to their directory."
        )
    if args.semantic:
        print(
            "Preparing the local multilingual model (first run downloads model and CPU runtime).",
            flush=True,
        )
        subprocess.run(
            [
                "uv",
                "run",
                "--group",
                "semantic",
                "python",
                "-m",
                "memora.services.embedding",
                "--warmup",
            ],
            cwd=ROOT / "apps/api",
            env=env,
            check=True,
        )
    subprocess.run(["docker", "compose", "up", "-d", "--wait", "db", "redis"], cwd=ROOT, check=True)
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=ROOT / "apps/api",
        env=env,
        check=True,
    )
    processes = []
    logs = ROOT / "data/web-trial-logs"
    logs.mkdir(parents=True, exist_ok=True)
    handles = []

    def launch(name, command, cwd):
        if args.semantic and command[:2] == ["uv", "run"]:
            command = [*command[:2], "--group", "semantic", *command[2:]]
        handle = (logs / f"{name}.log").open("w")
        handles.append(handle)
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        processes.append(process)

    def wait_ready(url, timeout=90):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if any(p.poll() is not None for p in processes):
                raise RuntimeError(f"A service exited. Inspect logs in {logs}")
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        if "/health" in url:
                            health = json.load(response)
                            if url.endswith("/ready"):
                                if any(
                                    health.get(key) != value
                                    for key, value in [
                                        ("database", "up"),
                                        ("redis", "up"),
                                        ("pgvector", "installed"),
                                    ]
                                ):
                                    raise RuntimeError(
                                        "API storage is not ready. Inspect service logs."
                                    )
                            elif health.get("status") != "ok":
                                raise RuntimeError("OCR inference failed. Inspect the OCR log.")
                        return
            except OSError:
                pass
            time.sleep(0.5)
        raise RuntimeError(f"Timed out waiting for {url}. Inspect logs in {logs}")

    def stop(_signal, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        launch(
            "ocr",
            [
                "uv",
                "run",
                "uvicorn",
                "app:app",
                "--app-dir",
                str(ROOT / "infra/ocr"),
                "--host",
                "127.0.0.1",
                "--port",
                "8081",
            ],
            ROOT / "apps/api",
        )
        wait_ready("http://127.0.0.1:8081/health")
        launch(
            "api",
            [
                "uv",
                "run",
                "uvicorn",
                "memora.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            ROOT / "apps/api",
        )
        wait_ready("http://127.0.0.1:8000/health/ready")
        launch("worker", ["uv", "run", "python", "-m", "memora.worker"], ROOT / "apps/api")
        if args.semantic:
            launch(
                "semantic-backfill",
                [
                    "uv",
                    "run",
                    "python",
                    "-m",
                    "memora.text_backfill",
                    "--all-devices",
                    "--watch",
                ],
                ROOT / "apps/api",
            )
        launch(
            "web",
            [
                "pnpm",
                "--filter",
                "@memora/web",
                "exec",
                "vite",
                "--host",
                "127.0.0.1",
                "--port",
                "5175",
                "--strictPort",
            ],
            ROOT,
        )
        wait_ready("http://127.0.0.1:5175")
        print(
            "Ready: http://127.0.0.1:5175\n"
            "Connect to local development server, then choose a folder.\n"
            + (
                "Real OCR, keyword and multilingual semantic search enabled.\n"
                if args.semantic
                else "Real OCR and keyword/document-type search; "
                "semantic and visual search are off.\n"
            )
            + "Local trial only. Keep this terminal running. Ctrl+C stops app services.\n"
            f"Logs: {logs}",
            flush=True,
        )
        while True:
            if any(p.poll() is not None for p in processes):
                raise RuntimeError(f"A service stopped. Inspect logs in {logs}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping web trial. Documents remain stored; database services remain running.")
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    main()

"""The server environment generator: random secrets, private file, no silent overwrite."""

import importlib.util
import stat
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "deploy_env.py"


@pytest.fixture(scope="module")
def deploy_env():
    spec = importlib.util.spec_from_file_location("memora_deploy_env", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _values(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)


def test_writes_a_private_file_with_distinct_random_secrets(deploy_env, tmp_path):
    out = tmp_path / ".env.production"
    assert deploy_env.main(["memora.example.com", "--out", str(out)]) == 0
    values = _values(out)
    assert values["MEMORA_DOMAIN"] == "memora.example.com"
    assert values["EMBEDDING_PROVIDER"] == "lexical" and values["WITH_SEMANTIC"] == "0"
    secrets_ = [
        values[k]
        for k in ("DB_PASSWORD", "APP_DB_PASSWORD", "OPERATOR_SECRET", "ENROLLMENT_SECRET")
    ]
    assert len(set(secrets_)) == 4 and all(len(s) >= 32 for s in secrets_)
    assert stat.S_IMODE(out.stat().st_mode) == 0o600


def test_semantic_search_is_opt_in(deploy_env, tmp_path):
    out = tmp_path / "env"
    deploy_env.main(["memora.example.com", "--semantic", "--out", str(out)])
    assert _values(out)["EMBEDDING_PROVIDER"] == "local" and _values(out)["WITH_SEMANTIC"] == "1"


def test_an_existing_file_is_never_overwritten_without_force(deploy_env, tmp_path):
    out = tmp_path / "env"
    deploy_env.main(["memora.example.com", "--out", str(out)])
    first = out.read_text()
    assert deploy_env.main(["memora.example.com", "--out", str(out)]) == 1
    assert out.read_text() == first
    assert deploy_env.main(["memora.example.com", "--force", "--out", str(out)]) == 0
    assert out.read_text() != first


@pytest.mark.parametrize(
    "bad", ["localhost", "not a domain", "http://x.com", "a..com", "bad-.example.com"]
)
def test_a_malformed_domain_is_refused(deploy_env, tmp_path, bad):
    assert deploy_env.main([bad, "--out", str(tmp_path / "env")]) == 2
    assert not (tmp_path / "env").exists()

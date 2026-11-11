"""The backup script's encryption and refusal rules, without needing Docker."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "backup.py"


@pytest.fixture(scope="module")
def backup():
    spec = importlib.util.spec_from_file_location("memora_backup_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_encrypted_round_trip_restores_the_exact_bytes(backup, tmp_path):
    plain = tmp_path / "data.bin"
    plain.write_bytes(bytes(range(256)) * 400)
    encrypted, restored = tmp_path / "data.enc", tmp_path / "restored.bin"
    backup.openssl("encrypt", plain, encrypted, "correct horse")
    assert encrypted.read_bytes() != plain.read_bytes()
    backup.openssl("decrypt", encrypted, restored, "correct horse")
    assert restored.read_bytes() == plain.read_bytes()
    assert backup.sha256(restored) == backup.sha256(plain)


def test_a_wrong_passphrase_is_reported_clearly_not_with_a_traceback(backup, tmp_path):
    plain, encrypted = tmp_path / "data.bin", tmp_path / "data.enc"
    plain.write_bytes(b"personal documents" * 100)
    backup.openssl("encrypt", plain, encrypted, "right")
    with pytest.raises(SystemExit, match="wrong passphrase"):
        backup.openssl("decrypt", encrypted, tmp_path / "out.bin", "wrong")


def test_a_backup_without_a_passphrase_is_refused_unless_explicitly_unencrypted(
    backup, monkeypatch
):
    monkeypatch.delenv("MEMORA_BACKUP_PASSPHRASE", raising=False)
    with pytest.raises(SystemExit, match="MEMORA_BACKUP_PASSPHRASE"):
        backup.passphrase(no_encrypt=False)
    assert backup.passphrase(no_encrypt=True) is None

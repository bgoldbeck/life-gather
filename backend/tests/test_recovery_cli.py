import io
import json
import sys
from pathlib import Path

import pytest

from lifegather.auth.store import AuthStore
from lifegather.config import Settings
from lifegather.recovery.__main__ import main
from lifegather.recovery.bundle import RecoveryService


@pytest.mark.parametrize("configuration", ["oauth-environment", "smtp-dotenv", "url"])
def test_verify_and_restore_do_not_require_lost_operational_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    configuration: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "source"
    store = AuthStore(source / "auth.sqlite3")
    store.migrate()
    bundle = tmp_path / "copy.lgbackup"
    phrase = tmp_path / "phrase"
    phrase.write_bytes(b"synthetic recovery passphrase")
    RecoveryService(Settings(data_dir=source)).create(bundle, phrase.read_bytes())
    monkeypatch.setenv("LIFEGATHER_DATA_DIR", str(source))
    monkeypatch.setenv("LIFEGATHER_CONFIGURATION_FILE", str(tmp_path / "lost.json"))
    if configuration == "oauth-environment":
        monkeypatch.setenv("LIFEGATHER_GOOGLE_CLIENT_ID", "SYNTHETIC_ID")
    elif configuration == "smtp-dotenv":
        for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_SENDER"):
            monkeypatch.delenv("LIFEGATHER_" + name, raising=False)
        (tmp_path / ".env").write_text(
            "LIFEGATHER_SMTP_HOST=synthetic.example.test\n", encoding="utf-8"
        )
    else:
        monkeypatch.setenv("LIFEGATHER_PUBLIC_URL", "SYNTHETIC_INVALID_ORIGIN")
    flags = ["--passphrase-file", str(phrase)]
    assert main(["verify", str(bundle), *flags]) == 0
    destination = tmp_path / "restored"
    assert main(["restore", str(bundle), str(destination), *flags]) == 0
    assert (destination / "installation.json").is_file()
    assert not (tmp_path / "lost.json").exists()
    # Backup must continue checking actual installation configuration.
    monkeypatch.setenv("LIFEGATHER_CONFIGURATION_FILE", "")
    rejected = tmp_path / "invalid-backup.lgbackup"
    assert main(["backup", str(rejected), *flags]) == 1
    assert not rejected.exists()
    output = capsys.readouterr()
    assert "SYNTHETIC_ID" not in output.out + output.err
    store.engine.dispose()


def test_isolated_verification_keeps_dotenv_storage_and_static_guards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "source"
    store = AuthStore(source / "auth.sqlite3")
    store.migrate()
    bundle = tmp_path / "copy.lgbackup"
    phrase = tmp_path / "phrase"
    phrase.write_bytes(b"synthetic recovery passphrase")
    RecoveryService(Settings(data_dir=source)).create(bundle, phrase.read_bytes())
    public = tmp_path / "public"
    public.mkdir()
    monkeypatch.delenv("LIFEGATHER_DATA_DIR")
    monkeypatch.delenv("LIFEGATHER_STATIC_DIR", raising=False)
    monkeypatch.setenv("LIFEGATHER_GOOGLE_CLIENT_ID", "SYNTHETIC_PARTIAL_ID")
    (tmp_path / ".env").write_text(
        f'LIFEGATHER_DATA_DIR="{source.as_posix()}"\n'
        f'LIFEGATHER_STATIC_DIR="{public.as_posix()}"\n',
        encoding="utf-8",
    )
    assert (
        main(
            [
                "verify",
                str(bundle),
                "--staging-dir",
                str(public),
                "--passphrase-file",
                str(phrase),
            ]
        )
        == 1
    )
    assert "static directory" in capsys.readouterr().err
    assert list(public.iterdir()) == []
    store.engine.dispose()


def test_cli_backup_verify_restore_and_secret_safe_failure_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source"
    AuthStore(source / "auth.sqlite3").migrate()
    monkeypatch.setenv("LIFEGATHER_DATA_DIR", str(source))
    monkeypatch.setenv("LIFEGATHER_GOOGLE_CLIENT_ID", "synthetic")
    monkeypatch.setenv("LIFEGATHER_GOOGLE_CLIENT_SECRET", "SYNTHETIC_GLOBAL_SECRET")
    phrase = tmp_path / "phrase"
    phrase.write_text("SYNTHETIC_RECOVERY_PASSPHRASE\n", encoding="utf-8")
    bundle = tmp_path / "copy.lgbackup"
    flags = ["--passphrase-file", str(phrase)]
    assert main(["backup", str(bundle), *flags]) == 0
    created = capsys.readouterr()
    assert json.loads(created.out)["operation"] == "backup"
    assert main(["verify", str(bundle), *flags]) == 0
    verified = capsys.readouterr()
    assert json.loads(verified.out)["database"]["users"] == 0
    destination = tmp_path / "restored"
    assert main(["restore", str(bundle), str(destination), *flags]) == 0
    restored = capsys.readouterr()
    assert json.loads(restored.out)["configuration_file"] == str(
        destination / "installation.json"
    )
    assert main(["restore", str(bundle), str(destination), *flags]) == 1
    rejected = capsys.readouterr()
    assert "new recovery destination" in rejected.err
    for output in (created, verified, restored, rejected):
        assert "SYNTHETIC_GLOBAL_SECRET" not in output.out + output.err
        assert "SYNTHETIC_RECOVERY_PASSPHRASE" not in output.out + output.err


@pytest.mark.parametrize(
    "value",
    [b"short", b"first synthetic line\nsecond synthetic line", b"x" * 1027],
    ids=["short", "multiline", "long"],
)
def test_invalid_passphrase_files_fail_before_creating_a_bundle(
    tmp_path: Path, value: bytes, capsys: pytest.CaptureFixture[str]
) -> None:
    phrase = tmp_path / "phrase"
    phrase.write_bytes(value)
    bundle = tmp_path / "copy.lgbackup"
    assert main(["backup", str(bundle), "--passphrase-file", str(phrase)]) == 1
    assert not bundle.exists()
    assert "Recovery failed" in capsys.readouterr().err


def test_interactive_confirmation_and_noninteractive_refusal_are_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = tmp_path / "copy.lgbackup"
    monkeypatch.setattr(sys, "stdin", io.StringIO())
    assert main(["backup", str(bundle)]) == 1
    assert "--passphrase-file" in capsys.readouterr().err

    class Terminal(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(sys, "stdin", Terminal())
    answers = iter(["synthetic first passphrase", "synthetic second passphrase"])
    monkeypatch.setattr("getpass.getpass", lambda _: next(answers))
    assert main(["backup", str(bundle)]) == 1
    output = capsys.readouterr()
    assert "do not match" in output.err and "synthetic first" not in output.err
    assert not bundle.exists()


def test_configuration_validation_does_not_print_supplied_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    configuration = tmp_path / "configuration.json"
    configuration.write_text('{"smtp_port":"SYNTHETIC_SECRET"}', encoding="utf-8")
    monkeypatch.setenv("LIFEGATHER_CONFIGURATION_FILE", str(configuration))
    assert main(["backup", str(tmp_path / "copy.lgbackup")]) == 1
    assert "SYNTHETIC_SECRET" not in capsys.readouterr().err

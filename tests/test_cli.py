import json

from typer.testing import CliRunner

from folava_mcp import auth
from folava_mcp.cli import app
from folava_mcp.config import Profile, save_profile

runner = CliRunner()


def test_config_contains_no_tokens(monkeypatch):
    monkeypatch.setenv("CANVAS_TOKEN", "very-private-secret")
    result = runner.invoke(app, ["config", "--profile", "school"])
    assert result.exit_code == 0
    assert "[mcp_servers.folava]" in result.stdout
    assert '"--profile", "school"' in result.stdout
    assert "very-private-secret" not in result.stdout
    result = runner.invoke(app, ["config", "--format", "json", "--demo"])
    assert result.exit_code == 0
    value = json.loads(result.stdout)
    assert "--demo" in value["mcpServers"]["folava"]["args"]


def test_login_requires_explicit_testing_mode():
    result = runner.invoke(app, ["auth", "login", "--url", "https://school.example"])
    assert result.exit_code == 1
    assert "--personal-token" in result.stderr


def test_masked_login(monkeypatch):
    monkeypatch.setattr(auth, "secure_keyring", lambda: object())
    received = []

    def login(origin, token, profile):
        received.append((origin, token, profile))
        return Profile("https://school.example", "personal-token", "a" * 32, "42")

    monkeypatch.setattr(auth, "login_token", login)
    result = runner.invoke(
        app,
        ["auth", "login", "--url", "https://school.example", "--personal-token"],
        input="private-secret\n",
    )
    assert result.exit_code == 0
    assert received == [("https://school.example", "private-secret", "default")]
    assert "private-secret" not in result.output


def test_errors_do_not_print_arbitrary_exception_or_secret(monkeypatch):
    def fail(profile):
        raise RuntimeError("private-token-and-upstream-body")

    monkeypatch.setattr(auth, "load_credentials", fail)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "private-token" not in result.output
    assert "Traceback" not in result.output


def test_status_never_reads_keyring(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLAVA_CONFIG_DIR", str(tmp_path))
    save_profile("school", Profile("https://school.example", "personal-token", "a" * 32, "42"))

    def fail():
        raise AssertionError("metadata listing must not unlock keyring")

    monkeypatch.setattr(auth, "secure_keyring", fail)
    result = runner.invoke(app, ["auth", "status"])
    assert result.exit_code == 0
    assert "https://school.example" in result.stdout


def test_invalid_config_format_is_actionable():
    result = runner.invoke(app, ["config", "--format", "xml"])
    assert result.exit_code == 1
    assert "codex" in result.stderr


def test_file_export_is_private_and_never_overwrites(tmp_path, monkeypatch):
    import hashlib
    import os
    import stat

    from folava_mcp import cli

    async def fake_fetch(profile, file_id, max_bytes):
        assert file_id == "42"
        return {"text": "assignment\n", "sha256": hashlib.sha256(b"assignment\n").hexdigest()}

    monkeypatch.setattr(cli, "_fetch_file", fake_fetch)
    target = tmp_path / "assignment.txt"
    result = runner.invoke(app, ["file", "42", "--output", str(target)])
    assert result.exit_code == 0, result.output
    assert target.read_bytes() == b"assignment\n"
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    result = runner.invoke(app, ["file", "42", "--output", str(target)])
    assert result.exit_code == 1
    assert target.read_bytes() == b"assignment\n"


def test_file_hash_mismatch_creates_nothing(tmp_path, monkeypatch):
    from folava_mcp import cli

    async def fake_fetch(*args):
        return {"text": "assignment", "sha256": "incorrect"}

    monkeypatch.setattr(cli, "_fetch_file", fake_fetch)
    target = tmp_path / "assignment.txt"
    result = runner.invoke(app, ["file", "42", "--output", str(target)])
    assert result.exit_code == 1
    assert not target.exists()

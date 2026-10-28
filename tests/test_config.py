import json
import os
import stat

import pytest

from folava_mcp.config import (
    ConfigError,
    Profile,
    load_profile,
    normalize_origin,
    read_token_file,
    remove_profile,
    save_profile,
)


@pytest.fixture(autouse=True)
def config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLAVA_CONFIG_DIR", str(tmp_path / "config"))


@pytest.mark.parametrize(
    "value",
    [
        "http://school.example",
        "https://user:password@school.example",
        "https://school.example/api/v1",
        "https://school.example?token=x",
        "https://school.example/#x",
        "https://school.example\\@evil.example",
        "https://school.example%2fevil",
        "https://school.example:bad",
    ],
)
def test_invalid_origins(value):
    with pytest.raises(ConfigError):
        normalize_origin(value)


def test_origin_canonicalization():
    assert normalize_origin(" https://SCHOOL.example:443/ ") == "https://school.example"


def test_profiles_contain_metadata_only(tmp_path):
    profile = Profile("https://school.example", "personal-token", "a" * 32, "42")
    save_profile("school", profile)
    assert load_profile("school") == profile
    path = tmp_path / "config" / "profiles.json"
    data = json.loads(path.read_text())
    assert data["version"] == 1
    assert set(data["profiles"]["school"]) == {
        "origin",
        "auth_kind",
        "credential_id",
        "user_id",
        "client_id",
        "redirect_uri",
        "scopes",
    }
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    remove_profile("school")
    with pytest.raises(ConfigError):
        load_profile("school")


def test_profile_path_traversal_rejected():
    with pytest.raises(ConfigError):
        load_profile("../outside")


def test_corrupt_config_not_overwritten(tmp_path):
    directory = tmp_path / "config"
    directory.mkdir()
    path = directory / "profiles.json"
    path.write_text("broken")
    with pytest.raises(ConfigError):
        save_profile("school", Profile("https://school.example", "personal-token", "a" * 32, "42"))
    assert path.read_text() == "broken"


def test_symlink_profile_rejected(tmp_path):
    directory = tmp_path / "config"
    directory.mkdir()
    target = tmp_path / "elsewhere"
    target.write_text('{"version":1,"profiles":{}}')
    (directory / "profiles.json").symlink_to(target)
    with pytest.raises(ConfigError):
        load_profile()


def test_secure_file_and_symlink(tmp_path):
    target = tmp_path / "token"
    target.write_text("personal-secret\n")
    target.chmod(0o600)
    assert read_token_file(target) == "personal-secret"
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(ConfigError):
        read_token_file(link)
    if os.name == "posix":
        target.chmod(0o644)
        with pytest.raises(ConfigError):
            read_token_file(target)


def test_token_file_rejects_directory_and_multiple_tokens(tmp_path):
    with pytest.raises(ConfigError):
        read_token_file(tmp_path)
    path = tmp_path / "token"
    path.write_text("one two")
    path.chmod(0o600)
    with pytest.raises(ConfigError):
        read_token_file(path)


def test_auth_and_resource_origin_port_policy_agree():
    from folava_mcp.config import normalize_origin
    from folava_mcp.policy import validate_origin

    for origin in ("https://canvas.example", "https://canvas.example:443/"):
        assert normalize_origin(origin) == validate_origin(origin)
    with pytest.raises(ConfigError):
        normalize_origin("https://canvas.example:8443")

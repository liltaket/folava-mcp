"""Non-secret profile metadata and private, atomic local configuration."""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit


class ConfigError(ValueError):
    """An actionable configuration error safe to show without a traceback."""


def validate_profile_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise ConfigError(
            "Profile names must contain 1–64 letters, digits, underscores or hyphens."
        )
    return name


def normalize_origin(value: str) -> str:
    try:
        url = urlsplit(value.strip())
        port = url.port
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or port not in (None, 443)
            or url.path not in ("", "/")
            or url.query
            or url.fragment
            or "\\" in value
            or any(ord(c) < 33 for c in value.strip())
            or "%" in url.netloc
        ):
            raise ValueError
        host = url.hostname.encode("idna").decode("ascii").lower()
        if ":" in host:
            host = f"[{host}]"
        return f"https://{host}" + (f":{port}" if port and port != 443 else "")
    except (ValueError, UnicodeError):
        raise ConfigError(
            "Canvas URL must be an HTTPS origin, for example https://school.instructure.com."
        ) from None


def config_dir() -> Path:
    override = os.environ.get("FOLAVA_CONFIG_DIR")
    if override:
        return Path(override).expanduser().absolute()
    if os.name == "nt":
        return (
            Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "folava-mcp"
        )
    if os.sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "folava-mcp"
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "folava-mcp"


def ensure_private_dir() -> Path:
    directory = config_dir()
    if directory.is_symlink():
        raise ConfigError("Configuration directory must not be a symbolic link.")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not directory.is_dir():
        raise ConfigError("Configuration location is not a directory.")
    if os.name == "posix":
        if directory.stat().st_uid != os.getuid():
            raise ConfigError("Configuration directory must belong to the current user.")
        directory.chmod(0o700)
    return directory


@dataclass(frozen=True)
class Profile:
    origin: str
    auth_kind: str
    credential_id: str
    user_id: str
    client_id: str | None = None
    redirect_uri: str | None = None
    scopes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if normalize_origin(self.origin) != self.origin:
            raise ConfigError("Stored Canvas origin is not canonical; sign in again.")
        if self.auth_kind not in ("oauth", "personal-token"):
            raise ConfigError("Unsupported authentication method; sign in again.")
        if not re.fullmatch(r"[a-f0-9]{32}", self.credential_id):
            raise ConfigError("Invalid credential reference; sign in again.")
        if not self.user_id or not isinstance(self.user_id, str):
            raise ConfigError("Missing Canvas identity; sign in again.")
        if self.auth_kind == "oauth" and (not self.client_id or not self.redirect_uri):
            raise ConfigError("OAuth profile is incomplete; sign in again.")
        if not isinstance(self.scopes, (tuple, list)) or any(
            not isinstance(x, str) for x in self.scopes
        ):
            raise ConfigError("Invalid OAuth scope configuration.")


def _read_profiles() -> dict[str, Profile]:
    path = config_dir() / "profiles.json"
    if path.is_symlink():
        raise ConfigError("Profile configuration must not be a symbolic link.")
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 1 or not isinstance(data.get("profiles"), dict):
            raise ValueError
        profiles = {}
        for name, raw in data["profiles"].items():
            validate_profile_name(name)
            raw["scopes"] = tuple(raw.get("scopes", ()))
            profiles[name] = Profile(**raw)
        return profiles
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise ConfigError(
            "Cannot read profile configuration. Restore a backup or sign in with "
            "a new configuration directory."
        ) from None


def list_profiles() -> dict[str, Profile]:
    return _read_profiles()


def load_profile(name: str = "default") -> Profile:
    validate_profile_name(name)
    try:
        return _read_profiles()[name]
    except KeyError:
        raise ConfigError(
            f"Profile '{name}' is not configured. Run folava-mcp auth oauth, "
            "or auth login --personal-token for local testing."
        ) from None


def _write_profiles(profiles: dict[str, Profile]) -> None:
    directory = ensure_private_dir()
    target = directory / "profiles.json"
    if target.is_symlink():
        raise ConfigError("Profile configuration must not be a symbolic link.")
    descriptor, temporary = tempfile.mkstemp(prefix=".profiles-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                {
                    "version": 1,
                    "profiles": {name: asdict(profile) for name, profile in profiles.items()},
                },
                stream,
                indent=2,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def profile_lock(name: str, *, metadata: bool = False) -> Iterator[None]:
    """Serialize refresh/config changes across locally launched MCP processes."""
    validate_profile_name(name)
    path = ensure_private_dir() / (".metadata.lock" if metadata else f".profile-{name}.lock")
    if path.is_symlink():
        raise ConfigError("Profile lock must not be a symbolic link.")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "r+b") as stream:
        if os.name == "nt":
            import msvcrt

            # Windows permits byte-range locks past EOF. Never initialize the
            # byte before locking: another process may already hold that range.
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def save_profile(name: str, profile: Profile) -> None:
    validate_profile_name(name)
    with profile_lock("profiles", metadata=True):
        profiles = _read_profiles()
        profiles[name] = profile
        _write_profiles(profiles)


def remove_profile(name: str) -> None:
    validate_profile_name(name)
    with profile_lock("profiles", metadata=True):
        profiles = _read_profiles()
        profiles.pop(name, None)
        _write_profiles(profiles)


def read_token_file(path: str | Path) -> str:
    """Read an owner-only regular file without following the final symlink."""
    try:
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or Path(path).is_symlink():
                raise ValueError
            if os.name == "posix" and (
                info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077
            ):
                raise ValueError
            value = stream.read(16385).strip()
            if not value or len(value) > 16384 or any(c.isspace() for c in value):
                raise ValueError
            return value
    except (OSError, ValueError, UnicodeError):
        raise ConfigError(
            "CANVAS_TOKEN_FILE must be a readable, non-symlink, owner-only "
            "regular file (chmod 600 on POSIX) containing one token."
        ) from None

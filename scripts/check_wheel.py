"""Smoke-test the CLI from the wheel built for this project."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WheelCheckError(ValueError):
    """The build output does not contain the expected wheel."""


def find_built_wheel(pyproject: Path, dist_dir: Path) -> Path:
    """Find the single wheel whose project name and version match pyproject.toml."""
    try:
        metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise WheelCheckError(f"Could not read project metadata from {pyproject}: {exc}") from exc

    project = metadata.get("project")
    if not isinstance(project, dict):
        raise WheelCheckError(f"{pyproject} has no [project] table.")
    name = project.get("name")
    version = project.get("version")
    if not isinstance(name, str) or not name:
        raise WheelCheckError(f"{pyproject} must declare a static project name.")
    if not isinstance(version, str) or not version:
        raise WheelCheckError(f"{pyproject} must declare a static project version.")

    wheel_name = re.sub(r"[-_.]+", "_", name).lower()
    if not dist_dir.is_dir():
        raise WheelCheckError(f"Build output directory is missing: {dist_dir}")
    wheels = sorted(path for path in dist_dir.iterdir() if path.is_file() and path.suffix == ".whl")
    if not wheels:
        raise WheelCheckError(f"No wheel found in {dist_dir}; run `uv build` first.")
    if len(wheels) > 1:
        found = ", ".join(path.name for path in wheels)
        raise WheelCheckError(f"Expected one wheel in {dist_dir}, found {len(wheels)}: {found}")

    wheel = wheels[0]
    project_prefix = f"{wheel_name}-"
    if not wheel.name.startswith(project_prefix):
        raise WheelCheckError(
            f"Wheel project name mismatch: pyproject.toml declares {name!r}, "
            f"but dist contains {wheel.name!r}."
        )
    expected_prefix = f"{wheel_name}-{version}-"
    if not wheel.name.startswith(expected_prefix):
        raise WheelCheckError(
            f"Wheel version mismatch: pyproject.toml declares {version}, "
            f"but dist contains {wheel.name!r}."
        )
    return wheel


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    try:
        wheel = find_built_wheel(ROOT / "pyproject.toml", args.dist).resolve()
    except WheelCheckError as exc:
        print(f"Wheel check failed: {exc}", file=sys.stderr)
        return 1

    uv = shutil.which("uv")
    if uv is None:
        print("Wheel check failed: `uv` was not found on PATH.", file=sys.stderr)
        return 1

    # Pass argv directly so paths with spaces and Windows executable paths are safe.
    result = subprocess.run(
        [uv, "run", "--no-project", "--with", str(wheel), "folava-mcp", "--help"],
        cwd=ROOT,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

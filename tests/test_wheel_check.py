import runpy
from pathlib import Path

import pytest

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/check_wheel.py"))
WheelCheckError = MODULE["WheelCheckError"]
find_built_wheel = MODULE["find_built_wheel"]


def project_file(tmp_path: Path) -> Path:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "folava-mcp"\nversion = "0.1.4"\n', encoding="utf-8")
    return pyproject


def test_finds_wheel_matching_project_name_and_version(tmp_path: Path) -> None:
    pyproject = project_file(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "folava_mcp-0.1.4-py3-none-any.whl"
    wheel.touch()

    assert find_built_wheel(pyproject, dist) == wheel


def test_reports_missing_wheel(tmp_path: Path) -> None:
    pyproject = project_file(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()

    with pytest.raises(WheelCheckError, match="No wheel found"):
        find_built_wheel(pyproject, dist)


def test_reports_multiple_wheels(tmp_path: Path) -> None:
    pyproject = project_file(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "folava_mcp-0.1.4-py3-none-any.whl").touch()
    (dist / "folava_mcp-0.1.3-py3-none-any.whl").touch()

    with pytest.raises(WheelCheckError, match="Expected one wheel"):
        find_built_wheel(pyproject, dist)


def test_reports_wheel_version_mismatch(tmp_path: Path) -> None:
    pyproject = project_file(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "folava_mcp-0.1.3-py3-none-any.whl").touch()

    with pytest.raises(WheelCheckError, match=r"version mismatch.*0\.1\.4.*0\.1\.3"):
        find_built_wheel(pyproject, dist)


def test_rejects_an_unrelated_package_wheel(tmp_path: Path) -> None:
    pyproject = project_file(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "unrelated_package-0.1.4-py3-none-any.whl").touch()

    with pytest.raises(WheelCheckError, match="project name mismatch"):
        find_built_wheel(pyproject, dist)

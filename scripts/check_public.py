"""Check public text for common credential and personal-path leaks, without echoing values.

This is a publication tripwire, not a general personal-data detector. Review names,
institution/account associations, screenshots and upstream payloads manually too.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = {
    "canvas_credential": re.compile(r"\b[0-9]{3,}~[A-Za-z0-9]{40,}"),
    "github_credential": re.compile(r"\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{30,}"),
    "private_key": re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"),
    "personal_path": re.compile(r"/(?:home|Users)/[^/\s]+/|[A-Z]:[\\/]Users[\\/][^\\/\s]+[\\/]"),
}
EMAIL = re.compile(r"(?<![:/\w.-])[A-Za-z0-9_.+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def findings(text: str) -> set[str]:
    result = {name for name, rule in RULES.items() if rule.search(text)}
    for match in EMAIL.finditer(text):
        domain = match[1].lower()
        if not (
            domain == "users.noreply.github.com"
            or domain in ("example.com", "example.org", "example.net")
            or domain.endswith((".example", ".test", ".invalid"))
        ):
            result.add("personal_email")
    return result


def check(site: Path | None = None) -> int:
    names = (
        subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT)
        .decode()
        .split("\0")
    )
    paths = {ROOT / name for name in names if name}
    if site is not None:
        if not site.is_dir():
            raise ValueError("The public build directory is missing.")
        paths.update(path for path in site.rglob("*") if path.is_file())
    failures = []
    checked = 0
    for path in sorted(paths):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        checked += 1
        for kind in sorted(findings(text)):
            # Names/categories only: never include a matched secret or source line.
            failures.append(
                f"{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path.name}: {kind}"
            )
    if failures:
        print("Publication check failed:\n" + "\n".join(failures))
        return 1
    print(f"Public-text checks passed ({checked} files). Manual privacy review is still required.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path)
    raise SystemExit(check(parser.parse_args().site))

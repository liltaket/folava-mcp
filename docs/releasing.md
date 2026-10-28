# Releasing

The release wheel is attached to a GitHub Release. There is no PyPI publish
workflow. The homepage installer is selected independently in `site/release.json`;
keep it and the pin in `docs/agent-setup.md` on the current published release
while preparing the next source version. Updating the Python project version does
not change the site installer.

## Prepare and validate the candidate

1. On a release pull request, update `[project].version` in `pyproject.toml` and
   add the corresponding `CHANGELOG.md` entry. Refresh `uv.lock` with `uv lock`.
   Leave `site/release.json` and `docs/agent-setup.md` on the currently published
   version.
2. Wait for the pull request checks to pass and merge it. Wait for CI on the
   resulting `main` commit to pass too. CI runs formatting, lint, tests, a
   package build and an installed-wheel CLI smoke check on Linux, Windows and
   macOS. CI runs for pull requests and `main`, not tags.
3. Tag that exact tested commit as `vVERSION` and push the tag. Use the commit
   SHA from its successful `main` CI run, and replace `VERSION` with the version
   in `pyproject.toml`:

   ```sh
   git fetch origin main
   git tag -a vVERSION <tested-commit-sha> -m "Folava MCP VERSION"
   git push origin vVERSION
   ```

4. Check out that tag in a clean working directory. Run
   the publication text check, build the artifacts, and smoke-test the wheel:

   ```sh
   uv sync --frozen
   uv build
   uv run python scripts/check_public.py
   uv run python scripts/check_wheel.py
   ```

   `check_wheel.py` reads the name and version from `pyproject.toml`, requires
   exactly one wheel in `dist/`, and installs that wheel into an isolated uv
   environment to run `folava-mcp --help`. If reusing a checkout, remove stale
   wheels from `dist/` first so the artifact count is unambiguous, or build with
   `uv build --out-dir /your/clean/output` and pass that directory to
   `scripts/check_wheel.py --dist /your/clean/output`. Review the
   wheel file listing with `python -m zipfile -l dist/folava_mcp-VERSION-py3-none-any.whl`
   and the source diff for unintended content; automated text checks cannot
   replace that privacy review.
5. Record and verify the wheel's SHA-256 before uploading it. For example, this
   Python command works across supported platforms:

   ```sh
   python -c "import hashlib; from pathlib import Path; p = next(Path('dist').glob('*.whl')); print(hashlib.sha256(p.read_bytes()).hexdigest(), p.name)"
   ```

6. Create the GitHub Release for `vVERSION`, attach the wheel produced from that
   tag, and include its SHA-256 in the release notes. Confirm the uploaded asset
   is downloadable at the URL the site installer will use before changing the
   site pin. GitHub's automatic source archive is not the installer wheel.

## Select and deploy the published release

After the wheel is publicly available, update `site/release.json` and the
version, tag URL and wheel URL in `docs/agent-setup.md` to that same published
version. Then build and validate the site:

```sh
uv sync --frozen --group web
uv run python scripts/build_site.py
uv run python scripts/check_public.py --site _site
uv run python scripts/build_site.py --verify-release
uv run python scripts/check_site.py
```

Merge the site-pin change to `main`. The Pages workflow checks that the selected
release wheel is available over HTTPS before it uploads or deploys the site, and
only its deployment job has Pages write access. If that check fails, correct the
asset or pin before deploying.

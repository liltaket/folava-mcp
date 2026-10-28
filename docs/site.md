# Documentation site

The public project site is https://liltaket.github.io/folava-mcp/.
GitHub Pages serves static files built by `.github/workflows/pages.yml`. It has
no Canvas connection, login handler, secret store, telemetry or model backend.
Do not place personal data in site assets or documentation examples.

The hand-authored visual source is in `site/`. `scripts/build_site.py` renders the
canonical repository Markdown into accessible pages and generates the API explorer
and `operations.json` directly from the operation registry. Built files go to
`_site/`, which is ignored by Git. There is no second copy of the API catalog or
user documentation to maintain.

```sh
uv sync --frozen --group web
uv run python scripts/build_site.py
uv run playwright install chromium
uv run python scripts/check_site.py
```

Browser checks use routed static files in Chromium without opening a web server.
They exercise example tabs and keyboard focus, clipboard success and denied-access
recovery, catalog search/details/empty results, document navigation and mobile
layout at 320/390 pixels. Use `--screenshots /your/review/folder` to save bounded
visual-review artifacts outside Git. Static tests also validate every internal
link and heading target for both project-path and relative-file builds.

On Linux CI, Playwright installs system dependencies with `--with-deps`.
Pull requests build and test the site; only `main` deploys to the `github-pages`
environment. The workflow uploads only `_site/` and grants deployment permissions
to its final job. Repository administrators select the Actions publishing source.
No custom domain is configured.

The homepage installer is selected explicitly in `site/release.json`, independently
of the Python development version. Publish the corresponding release wheel first,
then update this manifest. Main-branch deployment performs an HTTPS HEAD check and
fails before upload/deployment if the selected installer is unavailable. This
keeps a source-version bump from silently publishing a broken installation link.

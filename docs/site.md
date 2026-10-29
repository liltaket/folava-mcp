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

Guides and the API catalog share a reference layout with separate navigation.
Guide links are grouped by task, with an on-page contents list and adjacent-page
links. The catalog groups the registry's operations by resource while keeping
the operation IDs, parameters and examples intact. Navigation collapses into
native disclosures on smaller screens and remains available without JavaScript.

Styles, scripts and the generated favicon use content-derived URL versions so a
fresh page can request the matching assets after a deployment. The version is a
hash of the public asset, with no visitor or account identifier.

Cmd+K, Ctrl+K and the header search button open a native modal. The build generates
`search-index.json` from the deliberate document list and the operation registry,
using the same heading IDs as the rendered guides. Its content hash versions the
index URL. The browser fetches it on first use and ranks results locally. Queries
are not stored, added to URLs or sent to a search service; the hosting provider
receives an ordinary request for the public index. Results distinguish guides
from API operations, and operation links expand the matching catalog entry.
Failed index requests show a retry action; guide and catalog navigation remain
available independently of search.

The homepage's agent prompt points to `/install.md`, a deliberate plain-text copy
of `docs/agent-setup.md`. The same source renders as a normal documentation page.
Only this Markdown file is copied into the public build; private working files
are never copied wholesale. The guide's pinned installer must match the release
manifest, which the static tests enforce.

```sh
uv sync --frozen --group web
uv run python scripts/build_site.py
uv run python scripts/check_public.py --site _site
uv run playwright install chromium
uv run python scripts/check_site.py
```

Browser checks use routed static files in Chromium without opening a web server.
They exercise example tabs and keyboard focus, clipboard success and denied-access
recovery, catalog search/details/empty results, document navigation and mobile
layout and header touch targets at 320–1440 pixels. Theme checks cover the
sun/moon button, keyboard and touch activation, persistence across pages and open
tabs, OS changes before a choice, and blocked storage. Use
`--screenshots /your/review/folder` to save bounded
visual-review artifacts outside Git. Static tests also validate every internal
link and heading target for both project-path and relative-file builds.

Search checks cover both shortcuts, keyboard selection and focus, guide/API
navigation, catalog deep links, empty results, loading failure and retry. Static
checks validate every indexed result against its published page and section.

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

# Independent review

Reviewed working-tree changes against HEAD/base `36d7e07f2154885715928d0bc7274b40d7634b0c`, including untracked builder, site, workflow and tests. No repository edits or remote writes.

## Finding

**SHOULD-FIX (P2): coordinate the homepage installation command with publication of its wheel — scripts/build_site.py:40–44.** The homepage derives its primary install command directly from package version 0.1.1, producing `https://github.com/liltaket/folava-mcp/releases/download/v0.1.1/folava_mcp-0.1.1-py3-none-any.whl`. Pages deploys on every main push, independently of release publication. The task explicitly says no release has been performed yet. Deploying these changes before publishing that asset leaves the primary installation command unusable. Reproduction: build the site and inspect its installation command; the target is the unpublished version. Publish the matching wheel before Pages deployment, or use the documented source-install command until the release exists. This is a deployment ordering finding; remote asset availability was not queried.

No other actionable regressions established in the reviewed changes.

## Evidence and limits

- `.venv/bin/pytest -q`: **184 passed in 2.96s**, including callback socket tests, cancellation/stream-close tests, timeout propagation, and static site link/catalog checks.
- Built `/tmp/folava-review-site`: **14 pages, 103 catalog entries**.
- Browser check attempted against that output: **could not run**, because this existing `.venv` lacks `playwright` (`ModuleNotFoundError`). No socket-denial claim or browser-pass claim is made.
- Direct AsyncHTTPTransport retains default certificate verification; pinned destination IP and original hostname SNI remain set. Inspected installed httpcore connection implementation: `sni_hostname` reaches TLS `server_hostname`, with SSL context and timeout forwarded. Four explicit 20-second timeout extensions are preserved; aggregate deadlines and cancellation cleanup have passing deterministic tests. This is source inspection plus mocked transport evidence, not a live certificate/handshake or Canvas integration test.
- Static generation reads an explicit document list and public site assets rather than copying repository/configuration directories. No source credentials found in the inspected public inputs. Clean CI checkout builds only `_site` for upload. No live Pages deployment verified.

Next action: resolve the release/deployment ordering, install the web dependency group and run the browser check before claiming browser validation. Merge readiness: **88/100**, subject to those publication/validation steps.

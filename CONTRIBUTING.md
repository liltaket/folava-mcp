# Contributing

Start with a focused issue describing the student workflow, expected behavior and
an anonymized reproduction. Never include credentials, signed URLs, course bodies,
private submission material or another student's information.

```sh
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv build
```

Use a small pull request with a concrete before/after description and the checks
you actually ran. Distinguish fixture tests, protocol tests and live Canvas checks.
No live Canvas credentials are required by CI. Contributions are under Apache-2.0;
by submitting a change you confirm you have the right to contribute it.

## Adding API coverage

Add a fixed GET operation to `catalog.py`, link the official endpoint documentation,
and review parameter-side effects. Add per-operation query keys; avoid broad
wildcards. Check unread state, module completion and permissions explicitly.
Reject undocumented or ambiguous action endpoints until verified. Include a test
asserting the emitted method, path, accepted input and relevant unsafe variants.

The common policy must cover named tools, discovered reads, pagination and the
poller. File URLs must come from authenticated metadata and pass the same network
boundary. Credential operations belong in `auth.py` and never become agent tools.
Scope strings require exact official placeholders, not generated friendly names.

Prefer small dependencies, bounded resource use, actionable errors, and returning
source IDs/links. Do not hide permission failures or partial collections. Follow
[security reporting](SECURITY.md) for vulnerabilities and read the
[release gates](docs/release-readiness.md) before proposing deployment claims.

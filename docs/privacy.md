# Data handling

The project website is static. Its course examples are fictional, and it does
not connect to a student account or accept credentials. GitHub Pages still has
its own hosting and access-log behavior. Public documentation omits private
account, institution and local-machine details from validation reports.

The connector has no telemetry, analytics, advertising SDK, model SDK or hosted
Folava backend. It makes requested Canvas reads, attachment requests through API
pointers and S3, and explicit credential lifecycle requests. Normal DNS, TLS and Canvas
access logs still exist. Canvas may also refresh derived progress caches during
GET requests; the connector does not promise that remote account state is
unchanged. The [validation record](validation.md) explains the unresolved sampled
module-requirement signal.

Your MCP host sends selected tool inputs and Canvas results to the model provider
you use. Its storage, training and retention terms apply separately. This package
cannot promise that another provider will not retain or train on that content.
Use only a host and provider appropriate for your institution and the data involved.

Credentials are stored in the OS keyring, or supplied by the operator's environment
or protected token file. Metadata records the Canvas origin, user ID, OAuth scope
set and non-secret references. Polling stores hashes, query scopes, resource IDs
and event times/kinds. These are private metadata; hashes are not anonymization.
Exports store file bytes at a path you explicitly choose. MCP/API results are not
persisted by this package, but the host may keep transcripts and raw signed URLs.

Use `auth logout` to remove a stored profile and keyring credential, with `--revoke`
when you intend remote revocation. Delete your event SQLite databases and exports
when no longer needed. Remove injected secrets from their original source. Secure
backups, transcripts and credential-store retention are your operator's responsibility.

This document describes this package's behavior; it is not a policy for a hosted
commercial service. Such a service would need its own data terms and verified
institutional/API approval.

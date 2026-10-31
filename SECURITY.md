# Security

Folava MCP 0.1 is a development preview. Only the latest tagged preview receives
fixes. It has not been independently audited or approved by Instructure, and no
live institution compatibility is claimed by the automated test suite.

For a vulnerability, use [GitHub private vulnerability reporting](https://github.com/liltaket/folava-mcp/security/advisories/new).
If that form is unavailable, open a minimal issue requesting a private reporting
channel without including exploit details, tokens or student records. There is
no guaranteed response time. Do not test against accounts you do not own.

## Intended boundary

- Local stdio host and operating-system account are trusted. An agent that already
  has arbitrary shell access as that user may access their files/keyring; this
  connector cannot sandbox the host.
- Canvas origin is trusted operator configuration, never an MCP argument. Resource
  requests go through fixed reviewed GET routes and allowlisted query keys.
- Conversation detail forces `auto_mark_as_read=false`; submission `read_status`
  and `read_state` includes are rejected in initial and pagination queries. Known
  stateful assignment/module-item detail and quiz-submission routes are excluded.
  Direct page/front-page and individual revision reads are also excluded; see
  [the current catalog limits](docs/tools.md#excluded-reads).
- Public HTTPS destinations are DNS-pinned. API redirects are refused. Attachment
  content uses the fixed file `public_url` API pointer and audited AWS S3 REST
  destinations or the exact reviewed InstFS host/content capability described in
  [read safety](docs/research/read-safety.md), checked before every hop. Storage
  requests carry no Canvas authorization or cookies. Canvas UI/file-host downloads,
  other InstFS/CDN routes or hosts, custom and local-storage fallbacks are refused.
- OAuth callback state is verified. Credentials stay outside tool inputs, config
  snippets, event bodies and diagnostic messages. OAuth itself changes credential
  state separately from read-only learning-resource access.
- Attachments and course text are untrusted data. No content is executed and no
  shell hooks are provided. Opt-in PDF text extraction uses local Poppler processes
  with deadlines, output bounds and private temporary files. This is not an OS
  sandbox; keep Poppler updated. OCR and archive extraction are unsupported.

These controls limit resource actions; they do not promise an unchanged remote
account. Canvas GET handlers can write ordinary access logs or refresh derived
progress caches. One Canvas module-requirement comparison was inconclusive, with
neither the kind of difference nor its cause established. Direct page reads were
stopped conservatively, without claiming they caused the signal. See
[validation](docs/validation.md) for the bounded live evidence.

Raw upstream API fields may include signed attachment URLs, private grades, email
addresses or classmates' posts when the account can see them. A capable agent's
MCP transcript may retain these. Do not log, publish or share raw responses.

## Limitations and deployment

A compromised institution, local account, keyring or MCP host remains a serious
risk. Keep the package and operating system current. A personal token can carry
more upstream privileges than the connector uses. Do not deploy this stdio process
behind an unauthenticated network wrapper or share a server-wide Canvas token
between people. Multi-user hosting needs a separately reviewed authorization and
ownership boundary. See [release readiness](docs/release-readiness.md).

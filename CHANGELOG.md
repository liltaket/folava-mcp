# Changelog

## 0.1.2 — cross-platform authentication fixes

- Start the numeric loopback OAuth listener without a reverse DNS lookup, which
  could delay or prevent callback readiness on macOS.
- Acquire Windows byte-range locks without writing the locked byte first, so
  concurrent credential refreshes wait correctly instead of failing with access denied.
- Added a deterministic no-DNS regression; the existing concurrent-refresh test
  detected the Windows issue in hosted CI.

## 0.1.1 — deeper validation and documentation site

- Added GitHub Pages with installation, canonical documentation and a searchable
  operation catalog generated from the software registry.
- Fixed strict pagination parsing, malformed/complex JSON handling, quiz envelopes,
  partial downloads, multicast destination checks and signed-URL logging.
- Hardened OAuth callback parsing, GET scope validation and local lock safety.
- Kept meaningful link changes visible in polling while filtering signed URL noise.
- Made demo validation, dates and file limits reflect the real tool contract.
- Added one-session agenda reads with a 45-second total deadline and partial results.
- Expanded actual local HTTP/TLS, refresh concurrency, storage failure, protocol and
  browser interaction validation. See docs/validation.md for evidence boundaries.

## 0.1.0 — development preview

First public implementation: read-only Canvas operation catalog, student MCP tools,
OAuth and personal development auth, protected profiles, attachment export, synthetic
demo, and a replayable polling feed. Includes local security, protocol and package
checks. No PyPI publication, institutional approval, live Canvas compatibility or
hosted commercial readiness is implied. See docs/release-readiness.md.

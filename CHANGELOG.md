# Changelog

## Unreleased

- Tightened the desktop navigation and simplified its search control. Made the
  search dialog rounder and more compact, with five initial suggestions and
  shorter excerpts shown only after typing.
- Unified copy controls around the overlapping-square icon, with an in-button
  check and inline manual-copy help instead of a toast. Made the hero pencil
  more distinct and placed its drawing animation in front of the headline.
- Refined the mobile hero with a fluid two-line heading, a narrower reading
  column and a more compact setup note that brings the copy action into view sooner.
- Collapsed mobile navigation into a hamburger disclosure while keeping search
  and theme controls visible. Added keyboard dismissal, focus handling, responsive
  state reset and a script-free link fallback.
- Added a ChatGPT guide for private MCP tunnel setup, a synthetic first call,
  separate Canvas authentication and local desktop settings. Linked it from
  setup and included it in site navigation/search; ChatGPT verification remains pending.
- Added site-wide Cmd+K/Ctrl+K search for guide sections and API operations using
  a versioned public index and local ranking, with keyboard navigation and retry.
- Gave guides and the API catalog a shared reference layout with distinct grouped
  navigation, page contents, adjacent guides and expandable operation examples.
- Shortened homepage and catalog copy, clarified that the copy icon supplies the
  full setup prompt, and removed a repeated benefits section. Kept access and
  data-handling limits visible without promising unchanged Canvas account state.
- Refined the selected pencil hero: one curved lilac stroke, a detailed pencil
  that moves aside and fades, and a matching quiet button tint. Replaced the
  card-edge animation; reduced-motion readers receive the complete static mark.
- Replaced the theme menu with a sun/moon button. Mobile navigation puts the
  mark and theme button above a full-width row of links with larger text.
- Compacted the hero into a short installation row whose copy icon copies the
  complete agent prompt. The full text remains available in a disclosure and
  opens for manual copying if clipboard access fails. Shortened the introduction
  and theme control.
- Added an original note-sheet mark and neutral light/dark branding, with round
  translucent navigation and a solid reduced-transparency fallback.
- Kept copy labels stable and improved selection feedback when clipboard access
  is denied. Added clear/Escape handling and a no-script catalog fallback.
- Made documentation section headings linkable and kept navigation clear of
  the floating header. Added identity and release guidance.
- Standardized contributor text encoding and line endings. CI now selects the
  built wheel from project metadata instead of a manually updated filename.

## 0.1.4 — let your agent set it up

- Put a copyable setup prompt and a short agent-guide link on the homepage.
  Installation starts with the synthetic demo and preserves existing host config;
  the person's Canvas authentication remains a separate private step.
- Added a plain Markdown installation entry point and the matching readable guide.
  Manual terminal commands remain available alongside the agent flow.
- Made homepage language friendlier while preserving both themes, keyboard access
  and reduced-motion behavior.
- Anonymized validation narratives and removed institution and local-machine
  details from current public documentation and package metadata.
- Added publication checks for common credential/email/private-path patterns.
  These checks supplement manual privacy review and do not prove that historical
  copies or all personal information are absent.

## 0.1.3 — stricter reads and coherent themes

Upgrade from earlier previews before connecting a real account. HTTP GET alone
does not establish a read-only operation in Canvas.

- Excluded assignment and module-item detail routes that can mark progress, quiz
  submission routes that can grade or repair records, and submission `read_state`
  includes. Read assignments through the filtered collection instead.
- Excluded direct page/front-page reads conservatively after an inconclusive live
  progress observation; no page-GET causality is established. Read page bodies
  with `pages` / `group_pages` and `include[]=body` where permitted. Excluded
  individual page revisions because Canvas can repair revision records on GET.
- Fetch attachments through the permission-checked public URL API and direct S3
  REST storage only. Canvas download pages and unreviewed storage routes fail
  closed; signed URLs and credentials are never sent together.
- Added an opt-in live validation harness with an independent GET/API guard,
  request/deadline budgets and summaries without personal payloads. Progress
  comparisons distinguish membership, completion and requirement metadata.
- Added persistent System, Light and Dark themes across the site, first-paint
  initialization, restrained motion and reduced-motion support. Expanded browser
  checks cover contrast, keyboard use, mobile layouts and storage failures.
- Recorded actual deployment/stdio evidence and its limits in the test scenarios guide.
  Attachment content and unchanged account state have not been established by
  that live run.

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

# Release readiness

The source and synthetic demo are a development preview. Passing software checks
is not evidence of institutional approval, live account compatibility or a
commercially ready service.

## Implemented and locally testable

- Reviewed Canvas reads with an independently enforced resource policy.
- OAuth lifecycle, personal development credentials, profiles and protected storage.
- MCP workflows, bounded attachments, synthetic demo and durable polling/replay.
- Python package, locked development dependencies, CI and contribution guidance.

Exact validation evidence is recorded in [validation](validation.md).

## External launch gates

1. Establish Instructure approval/terms applicable to this MCP integration. Current
   [API policy §3(i)](https://www.instructure.com/policies/canvas-api-policy)
   explicitly addresses MCP. No exception is assumed for open source or personal
   hosting, and an institution developer key is not proof of approval.
2. Provision a scoped institution developer key, exact registered callback, and
   a deployment that can protect its confidential secret. Demonstrate consent,
   refresh, logout and revocation with a real test account.
3. Compare real unread conversation/submission state before and after controlled
   reads in an appropriate test course, isolating one action per comparison.
   Include module progress as well as unread state. The recorded Canvas requirement
   comparison is inconclusive; neither page causality nor account invariance was
   established. Mock request assertions do not prove remote state behavior.
4. Validate actual course permissions, endpoint scope compatibility, file storage
   compatibility and calendaring for the target institution. Attachment support
   requires supported S3 or the reviewed InstFS content path. A bounded authorized
   sample downloaded PDFs through InstFS/CDN and extracted text; it does not
   establish support for other backends or unrestricted page access.
5. Test installation and complete workflows in the target Codex and T3 Code hosts.
   SDK stdio tests do not establish all host-specific behavior.
6. Before selling a hosted service, define operator ownership, consent, data
   handling and incident processes. Network hosting, per-user MCP auth, account
   isolation and billing are outside this preview.

These gates cannot be cleared by writing more local code. Do not advertise an
approved integration or ask customers for manually generated tokens while they
remain open. The implementation does not attempt to bypass these restrictions.

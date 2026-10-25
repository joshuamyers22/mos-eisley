# Credential boundary work note

Status: CLOSED. Implementation and source/installed verification complete. Requirement: plan §31.5.

Guidance selected: Python engineering guide, bounded verification guide/loop,
threat-model template, adversarial review playbook and ADR template, using the
repository's pinned production-project-template guidance.

Objective: typed owner-scoped references resolved only by trusted host networking;
exact approved provider operations, pinned DNS/address/TLS, no redirects/proxies,
no retries, live rotation/revocation, no change to recovery or publisher authority.
High-risk credential boundary: implementation and executable evidence do not
constitute accountable production/release approval.

Rubric: block on credential egress outside the approved socket, owner/scope/expiry
bypass, replay of consumed broker operations, leaked exceptions/responses or
unbounded I/O. Evidence: adversarial tests, real synthetic-credential loopback
capture, existing broker/spend/recovery regressions, source and installed gates.
Budget: three evidence-changing implementation/review passes, one complete gate,
focused corrections as needed; no paid calls, real credential inspection or release.
Stop on passing gates or document a concrete unresolved boundary.

Architecture: additive host transport; legacy paths remain supported and default
until separately credentialed provider/tool conformance and accountable admission.

Evidence-changing passes: (1) typed native holder and pinned transport with real
socket negatives; (2) broker/spend composition, interruption and mid-write lifecycle
races; (3) adversarial diagnostics/TLS environment review and artifact verification.
The diagnostics pass fixed echoed-header debug logging. Its final TLS correction
removed ambient key logging from default context construction. All 20 focused
checks then passed; the initial combined gate was interrupted for that correction
and rebuilt before restarting. No security control was skipped or relaxed.

Final full-gate result and accountable activation limits are recorded in
`CREDENTIAL_BOUNDARY_VERIFICATION.md`. Existing credential defaults remain intact.

The parallel combined gate failed in existing timed review/calibration fixtures
and missing SDK metadata, rather than the new acceptance cases. This justified one
bounded fixture-isolation pass: fresh-wheel groups of 37, 53 and 234 checks passed;
the last checked SDK metadata after each case. Final native-read expiry guard and
boolean-only environment inspection passed affected static checks and 21 focused
cases. A sequential normal full gate is required for closeout; no live authority,
production checks or security limits were weakened to make fixtures pass.

Closeout: the final standard `make check -j1` passed with 3,814 source tests,
17 existing skips, 85% coverage, 2,781 installed-wheel tests and 13 existing skips.
Full lint/format, strict typing, frozen export and wheel/sdist build passed.
The proxy trap's connection counter was then strengthened without changing the
application. Affected static checks and 21 source plus 21 fresh-wheel acceptance
checks passed. Application module bytes match the tested final wheel. Existing
credential defaults and exact live/platform/accountable activation gates remain.
No provider call, credential inspection, production activation or release occurred.

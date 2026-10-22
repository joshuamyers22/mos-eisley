# Credential boundary verification

Requirement: plan §31.5. Branch: `feat/credential-boundary`, based on
session-recovery commit `d1ccf82`. Implementation uses the repository's pinned
production-template Python, threat-model, ADR, adversarial review and bounded-loop
guidance. No real credentials, native vault contents or paid provider requests were
used. Synthetic socket captures remain disposable test data outside tracked files.

Focused evidence: 21 credential-boundary acceptance tests passed natively on macOS.
The tool sandbox cannot bind local sockets, so socket checks require native execution.
An initial fixture cleanup deadlock was fixed; no security checks were skipped.
Additional review found response headers could echo credentials into HTTP debug
logs; task-local producing-logger suppression and an adversarial echo test close
that path. Static checks passed for the affected modules and test.

The tests exercise real HTTP and TLS sockets, original-host certificate checks,
DNS address drift, redirect/proxy traps, model/tool destination and marker injection,
native owner/scope/expiry checks, rotation/revocation, header/body races, blocked-read
cancellation/deadline, body/header echo, malformed/oversized responses and invalid
counts. They compose the new transport with the actual spending ledger and request
broker, retain conservative uncertain exposure after a lost response, reject claim
replay after rotation and scan saved evidence/debug output/child environments for
the synthetic keys. The same file is explicitly included in installed-wheel smoke.

The first combined gate was deliberately interrupted when review found Python's
default TLS context helper could honor `SSLKEYLOGFILE`. Explicit client TLS context
construction and a real-TLS environment-injection assertion close that path.

The parallel full gate did not pass: 3,813 source tests had four failures and six
errors (17 existing skips); 2,780 installed tests had seven failures and 162 errors
(13 existing skips), clustered in existing timed review/conformance fixtures and
missing SDK version metadata. The new credential acceptance cases passed. A fresh
wheel ran 37 credential/probe checks, then 53 including campaign ceremony, and an
ordered 234-test diagnostic with SDK metadata checked after every case; all passed
(the 234-test diagnostic retained eight platform skips). No runtime checks or
credentialed conformance requirements were relaxed.

A final expiry guard now rechecks native-key expiry after the store read, before
any header write. The 21 focused socket tests and affected static checks passed.
The environment-inspection fixture returns only a boolean; it does not return raw
environment values. After the complete gate, the proxy fixture was strengthened to count connections
to the trap separately and assert zero. The application code did not change.
Affected lint/format/strict typing passed, then all 21 focused cases passed again
from source (0.609 seconds) and a fresh installed wheel (0.785 seconds).
The three application modules were compared byte-for-byte with the tested wheel.

Final sequential gate: source/static/package stages passed. The source run
completed 3,814 tests in 3,459.198 seconds, with 17 existing platform skips and
85% branch-inclusive coverage. Repository lint/format, strict typing, locked
runtime-export verification and wheel/sdist build passed. The fresh installed-wheel
suite passed 2,781 tests in 2,255.360 seconds with 13 existing platform skips.
`make check -j1` exited 0. No test or security boundary was skipped to obtain this
result beyond those existing platform skips.

Tested final wheel SHA-256:
`ff72c504083589b54fd362df845cb14407596a71877f92be8c974a02c6d2d293`. The gate builds a wheel/sdist, runs repository
lint/format, strict typing, source coverage, locked dependency-export checks and
fresh installed-wheel tests. The final run uses ordinary `make check -j1`, preserving
source/coverage, build and installed-wheel order without parallel test contention.

Limits: fixture captures prove the implemented local boundary, not a live service
qualification or deployment. Native-store lifecycle administration remains trusted;
this feature adds only a reader. Current CLI key/SDK paths remain default. Existing
exact provider/tool credentialed conformance, target-platform and accountable
security/release approval gates still apply before production activation.

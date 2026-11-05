# rc.15 protected signing and affected qualification

- Status: affected signed qualification complete; publication is separately gated.
- Owner: Joshua Myers; operator Codex. Started 2026-11-05 UTC.
- Review by: 2026-11-12 or frozen-candidate change.
- Frozen candidate: `21fc2b02db5611d806626ad8c70698b3c7181577`, version
  `0.1.0-rc.15`, storage epoch 2; tag object
  `ac6627da26ce8ab1488197fbd525fe7f7def93e7`.
- [PR #363](https://github.com/joshuamyers22/mos-eisley/pull/363) merged normally as
  `83055ed6b5afe492670661ebe0cfe3b7b71f1307`; its tree equals the reviewed candidate.
- [Protected run 41948231550, attempt 1](https://github.com/joshuamyers22/mos-eisley/actions/runs/41948231550)
  uses workflow `350992511` on the exact immutable tag/source.

## Authority, objective and review

The owner explicitly requested owner review and merge, protected signing and
fresh affected rc.15 qualification. This authorizes the stated signing and
qualification scope. Publication remains for disposition of the resulting evidence.
No fresh provider invocation, native grant renewal or historical replay is part
of this scope. This is an owner-directed operator review, not an independent
human security attestation.

Selected guidance: repository adversarial and bounded-verification guides,
review/verification-loop/threat-model/work-note templates, and publisher runbook.
Risk: material release/supply-chain boundary. One technical trace and one actual
signed-artifact reconstruction add evidence beyond the implementation review.
Ceilings: six-hour wall/monotonic window, one protected run attempt, zero model
calls. Stop on identity/hash mismatch, failed required gate, cleanup failure or
budget ceiling; preserve the first failure rather than silently retrying.

Technical review traced recursive metadata collection, actual interpreter probes,
locked target dependency closure, bounded non-executing archive readers, exact
source/version/platform/hash bindings, typed canonical SBOM admission before
GitHub API calls, and build/download/sign/inventory/qualification ordering.
No blocking finding remains. Unknown native-library versions remain hashed file
identities; declared license inventory is not legal or vulnerability clearance.
Runtime dependency selection/export and historical rc.14 assets stay unchanged.

All 21 exact-head candidate checks pass: 3,948 source tests (17 skips), 86%
coverage; 2,916 wheel tests (13 skips); four native builds and combined SBOM
coverage. Audit found no known vulnerability or adverse project status in 54
packages. The prior local controller's post-test Python 3.9 receipt-writer
failure remains preserved; its uncaptured gate exit is not claimed. Final-head
CI supplies captured outcomes. See [candidate work note](RC15_SBOM_WORK_NOTE.md)
and the [final CI](https://github.com/joshuamyers22/mos-eisley/actions/runs/41935046461).

## Protected preparation and qualification rubric

GitHub's approval history records `joshuamyers22` approving `application-release`
for this run. The environment still requires that owner, permits solo-owner
self-review and disallows administrator bypass. No custody value is inspected.
All four tagged native jobs, secret scanning and the all-target inventory
check pass. Protected preparation completed `make check audit`, the container
gate, enrolled signing and canonical inventory generation. Its captured results
are 3,948 source tests (17 skips, 86% coverage), 2,916 wheel tests (13 skips),
and no known vulnerability/adverse status across 54 audited packages. This is a
captured successful protected gate on the actual frozen candidate, independent
of the earlier local receipt-writer failure.

Acceptance requires actual signed installation on macOS/Linux arm64/x86_64,
both-store cold resume/terminal/diff/recovery, actual immutable rc.14 upgrades,
all historical refusal/upgrade journeys including rc.7 downgrade refusal, offline
native diagnostics with replay immutability, both macOS formula journeys, and
actual signed SBOM coverage/hash/source checks. Actual reconstruction admitted all 58 reports and 76 prepared assets, validating
all candidate/source/hash/harness bindings, comparing all 418 packaged runtime
source files on each target, and authenticating all eleven
immutable predecessor metadata/checksum sets. The SBOM has 6,485 components and
6,486 dependency records; Linux covers 44 selected locked packages per target and
macOS covers 42. See the [evidence review](RC15_QUALIFICATION_REVIEW.md).

## Handoff

All four signed jobs passed; the last completed at 04:46:10 UTC, inside the
initial six-hour execution ceiling. The asynchronous operator wait exceeded that
observation window; no replacement run or native qualification was launched.
A separate bounded one-hour read-only closeout resumed at 13:26 UTC, auditing
retained completed artifacts and writing scratch controls/receipts only.

The first historical-metadata review used the strict epoch-2 publication parser;
it correctly refused epoch-1 metadata. Review was corrected to the existing
`parse_retained_release` authenticator for historical inputs only. The original
refusal is preserved; no product parser, signed input or qualification report was
changed. Completed-job logs were retrieved through the job API because the whole
workflow remains pending at publication; ANSI bytes stayed in a private file.

Actual signed SBOM recomputation, offline official-schema validation, independent
standard marker/reader comparisons and five malformed-inventory refusal controls
pass. The read-only stdlib publisher preflight also exits 0. The frozen source,
all 76 retained asset bytes and historical rc.14 SBOM remain unchanged. No provider
call, grant renewal, signing-key read or administrative bypass occurred.

Publication remains pending owner approval in `application-release`; this task
does not approve that deployment. rc.14 live qualification remains historical
evidence; no fresh rc.15 live subscription campaign or stable-v1 qualification
is claimed. The evidence review is ready for publication disposition.

# G4 initial correction final whole-suite authorization

## Scope and invariants

Prepare owner authority for one offline pair of creator and reviewer whole-suite
runs on correction commit `e90c3bbe3c795bb4788f2454c5fc9ba221ad7663`, linked to
verified passing candidate receipt
`51c9c2ae70b6b6f6075c21a9ff7f821be6fe3354322fdacab6e732838c7b9454`.
No task suite executes during preparation or signing. Provider calls, Git writes,
independent-review approval and G4 acceptance remain outside the grant.

Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`,
and `templates/THREAT_MODEL.md`. Risk: high, an exact test authorization boundary.
Reuse `docs/G4_FINAL_WHOLE_SUITES_THREAT_MODEL.md`; the owner key, same-UID host,
pinned Git and container runtime remain trusted. No independent human review is
claimed. Sampling artifacts remain outside scope.

Replay the candidate claim, correction VCS signature and chain, frozen tests,
binding, controls and clean Git. Verify creator bytes against the original base,
initial child commit and corrected commit. Freeze distinct creator/reviewer
requests and a creator package containing the complete protected inventory.
Reuse the established final whole-suite schema/domain; its suite ID includes the
full SHA-256 of the private final-store path to bind this authority to one store.
Reject state, scope, image, signer or deadline changes. Stop after focused checks,
real-chain preflight and owner signature; publication requires the combined gate.

## Frozen execution subjects

The unchanged creator test inventory contains 13 tests; the existing blind
reviewer package contains 16. Preparation ran neither suite. Exact hashes:

- Creator package: `e994e831f1cf25ea6407647c30449f745da56b754e01d992f5ca7435c5b9402b`
- Creator request: `9d1044ffb0c1cc5a358164146d22c6ea90f95d76121336947eae336f7747ea89`
- Reviewer request: `4b508b5a1d62dbc34407fa169058b7e24cdddbbdebd9da0198296580c29db06b`
- Creator job: `40a77e6a2864bd1b944561f1691dff01105cb5cccbbf06b63c992f01050e11a1`
- Reviewer job: `0b05467b2e163ca6b9f8793e04f1925b2d665173160fce5f846191473da230aa`

Real-chain preparation and preflight passed. The focused deadline/store/request
substitution test, Ruff and Pyright passed. The identifier prefix was shortened
to fit the 80-character contract while retaining the full store SHA-256.

The owner signed
`/Users/josh/.mos-eisley-g4-distinct-deps-2026-09-30/signed-deps12-final-whole-suite-approval-1.json`.
Its artifact SHA-256 is
`58fc2f4824ea456b513b8fab2245ac35340b2c73e2887df701166f15006a3667`.
The signature and complete read-only preflight passed. The file is owner-private
mode 0600. Its authority window is September 30, 2026 22:23:43 UTC through
October 1, 2026 00:23:43 UTC. No final whole-suite execution occurred.

## Authorized execution

The owner requested consuming the exact signed authority and running both frozen
final suites. Persist a candidate-keyed claim before the creator job; then run
the creator and reviewer jobs separately, compare reviewer test identities with
the passing candidate, and replay both receipts and unchanged Git. Reject claim
reuse or inadequate remaining time. No retry or acceptance follows from this run.

### First pair startup failure

Attempt one durably consumed its grant but the creator worker failed without
returning an execution receipt. The reviewer worker was not reached. No final
pair receipt exists, so no success or measured creator counts are claimed. The
cleanup lifecycle records show the attempted container was removed.

A separate offline diagnostic decoded the exact job without running tests and
inspected the pinned worker and stdlib loader. The frozen creator package has
only `tests/test_order.py`; discovery used start `tests`, top `.` and requires
`tests/__init__.py`, which is absent. This establishes a discovery configuration
defect. A new preflight check rejects missing package initializers without
importing task tests. The focused regression covers both the rejected original
configuration and a valid top `tests` configuration.

Preserve the spent first claim and all frozen inputs. Prepare distinct second
pair inputs/requests/store with creator discovery top `tests`; all creator test
bytes and the original blind reviewer package remain unchanged. The revised
creator package and jobs need a fresh owner signature before either suite runs.

### Second pair completed

The owner signed the revised pair authority with artifact SHA-256
`03891cb38ab829d73171a578d6ac8711ee63fdfd80823c54eb14575349a7e0c0`.
Its window is September 30, 2026 22:38:11 UTC through October 1, 2026
00:38:11 UTC. Signature and full chain preflight passed. The revised creator
package SHA-256 is
`d8a39c33ead2a0ebd7dae498ddb4689f11c944850eb88a483d4d0fedb99d4977`.
Creator test bytes and blind reviewer package were unchanged.

The broker consumed the fresh claim at September 30, 2026 22:42:19 UTC and
completed both frozen suites. All 13 creator and 16 reviewer tests were
collected, started and executed, with zero failures, errors or skips. Reviewer
test identities match the passing corrected candidate. Individual stage receipts
are retained before subsequent work, using owner-private, exclusive writes;
verification rejects overwritten or substituted stage evidence.

The final pair receipt is
`/Users/josh/.mos-eisley-g4-distinct-deps-2026-09-30/deps12-final-whole-suite-receipt-2.json`,
SHA-256 `c46955a60e252037ea3e002640e1e31caeea928d19c9866c0a79b49998dc9ec8`.
The runner verified the claim, both retained stage receipts, measured results,
exact requests, full correction provenance and unchanged task Git after execution.
Claim, stage and pair files are mode 0600. The first spent grant remains intact.
No provider call, task Git write, independent-review approval or G4 acceptance
occurred. Independent review and acceptance remain outstanding.

The three focused controller tests, Ruff formatting/lint and Pyright passed.
The combined repository publication gate remains required before publishing.

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
to fit the 80-character contract while retaining the full store SHA-256. The
creator signature is pending. No final whole-suite execution occurred.

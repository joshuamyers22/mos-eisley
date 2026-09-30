# G4 initial-correction integration authority work note

## Objective and scope

Prepare an owner-signed, exact offline integration grant for the dependency
ordering correction proposal. Authorization alone performs no Git write. The
future one-use broker must create a private detached worktree, apply only the
signed replacement, check the resulting parent/path/blob/patch and obtain a
separately signed VCS record. It may not alter the original checkout, call a
provider, run final suites, merge, push or accept G4.

Parent controller commit: `9f79cdf58f88e4d5a5fbe2e9e4b1373dc4020370`.
Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`,
`templates/AGENTIC_VERIFICATION_LOOP.md`, and `templates/THREAT_MODEL.md`.
Risk class: high because the artifact grants an isolated Git write. This work
reuses the [correction integration threat model](G4_CORRECTION_INTEGRATION_THREAT_MODEL.md)
and the [initial integration contract](G4_INITIAL_INTEGRATION.md). Sampling
artifacts are outside scope.

## Invariants and evidence

The grant binds the signed initial correction admission, correction-child
dispatch and measured production receipts, original provenance policy, exact
integrated source commit and root path, private integration store path, exact
changed paths, and a bounded UTC window. Replay checks the existing one-use
dispatch claim, settled provider ledger, unchanged clean integrated checkout,
and bounded safe Git tree. The approval uses a new signature domain so another
G4 approval cannot be substituted.

Stop on a changed chain, source, test, store, policy, path, signature, deadline
or ledger. The same-UID host, Git executable, Docker image and owner key custody
remain trusted. The owner's single-operator signature does not claim independent
human review.

## Authorization result

The owner signed the exact grant at
`/Users/josh/.mos-eisley-g4-distinct-deps-2026-09-30/signed-deps12-correction-integration-grant-1.json`.
Its SHA-256 is
`cd639ec385aa460084fea09f87dfd0332f2225319bf25c4c9ebca7db3f583248`.
The read-only `status` verifier replayed the correction chain and signature
successfully. The focused authority tests, Ruff, and Pyright passed.

## One-use integration

The broker consumed the grant with an owner-private one-use claim and committed
the exact correction to a detached worktree. Its parent is
`9bece145bdcd8047e19393fc39ae27f8ad09a45c`; its commit is
`e90c3bbe3c795bb4788f2454c5fc9ba221ad7663`. The unsigned integration
record SHA-256 is
`21c480ba5f6d8a6fdd01bb6e6ed2288e1c9c844e778aef3e3df9731d2cb97bc1`.
Replay found only `src/dependency_lab/order.py` changed, matching the signed
proposal bytes. The original checkout stayed clean. The separate VCS signature
is pending. No task test, provider call, or G4 acceptance occurred.

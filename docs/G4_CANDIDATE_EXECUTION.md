# G4 candidate execution admission and dispatch

This fifth offline G4 slice permits one separately approved candidate reviewer-test
run after the frozen package, exact implementation binding, paired known controls,
authenticated custody and trusted Git/E2 provenance are replayed. It executes only
through the existing immutable-image, no-mount, network-disabled container. The
receipt is test evidence, not correction or implementation acceptance.

## Separate exact approval

An enrolled creator signs a canonical `G4CandidateExecutionApproval` with the
`mos-eisley/g4-candidate-execution-approval/v1` Ed25519 domain. It binds the exact
authenticated-provenance record, control record, candidate request, repository ID,
source revision, image ID, trust policy and a positive window of at most 24 hours.
The request fixes the candidate role, execution ID, binding hash, image and 5–60
second deadline. The signature must follow the child result chronologically and be
valid at dispatch under the policy window. No production command accepts a private
key; signing is an external creator-custody operation.

Earlier G4 artifacts explicitly deny candidate authority. The approval grants
only this one offline test run. It never permits child/model/provider dispatch,
repository or VCS writes, credentials, network, correction or acceptance. A local
clock limits use but is not an external trusted timestamp. Single-operator custody
still discloses self-review risk and does not constitute independent review.

## Admission and one-use dispatch

Preflight verifies signatures, exact lineage, controls, package, binding, current
read-only Git reconstruction and a clean bound worktree. It writes a canonical
admission record but performs no test run. Dispatch repeats that preflight and then
exclusively writes a private claim named for the signed approval in an existing,
controller-owned mode-`0700` store. A duplicate or concurrent attempt fails; a
crash or infrastructure failure after the claim consumes the approval and requires
a new signed approval. The store must be persistent and unique to the controller;
switching stores bypasses the local replay guard and is outside this boundary.

Only after the claim does the runner send the exact bound source/resource bytes and
frozen reviewer package to the approved image. The generic G4 isolated-run command
now rejects `candidate` requests; known-good/known-bad controls remain available.
The runner compares exact collection and outcome counts, rebuilds the execution job
after the container returns, and reconstructs current Git again. A failed candidate
suite produces a retained receipt with `candidate_tests_passed=false`; it never
implies a defect diagnosis or authorizes a correction. A drift, timeout, malformed
observation or infrastructure failure fails closed and may leave a spent claim but
no completion receipt.

All input artifacts, admission, receipt, lifecycle records and dispatch store stay
outside the repository. The host controller, Git binary/object store, Docker daemon,
exact image, kernel, local clock and same-UID storage remain trusted. The image's
dependency correspondence to declared locks is not proven by this slice.

## Commands

Prepare a signed approval and a canonical `ReviewerTestExecutionRequest` with
`role="candidate"`, plus a persistent private dispatch store. All paths below are
examples and must be outside the implementation repository except the two roots:

```sh
uv run --frozen mos g4-check-candidate-execution \
  --approval signed-candidate-approval.json \
  --request candidate-request.json \
  --provenance authenticated-provenance.json \
  --controls known-controls.json \
  --binding immutable-implementation-binding.json \
  --reviewer-package frozen-reviewer-package.json \
  --repository-root /absolute/repository \
  --implementation-root /absolute/repository \
  --git /absolute/path/to/git \
  --output candidate-admission.json

uv run --frozen mos g4-dispatch-candidate-execution \
  --admission candidate-admission.json \
  --provenance authenticated-provenance.json \
  --controls known-controls.json \
  --binding immutable-implementation-binding.json \
  --reviewer-package frozen-reviewer-package.json \
  --repository-root /absolute/repository \
  --implementation-root /absolute/repository \
  --git /absolute/path/to/git \
  --docker /absolute/path/to/docker \
  --dispatch-store /private/persistent/candidate-claims \
  --lifecycle-root /private/container-lifecycles \
  --output candidate-receipt.json

uv run --frozen mos g4-verify-candidate-execution \
  --receipt candidate-receipt.json \
  --provenance authenticated-provenance.json \
  --controls known-controls.json \
  --binding immutable-implementation-binding.json \
  --reviewer-package frozen-reviewer-package.json \
  --repository-root /absolute/repository \
  --implementation-root /absolute/repository \
  --git /absolute/path/to/git \
  --dispatch-store /private/persistent/candidate-claims
```

All outputs are canonical, private mode-`0600` and never overwrite an existing
path. Receipt replay checks the exact persisted dispatch claim and current inputs;
it permits inspection after the approval window expires. A nonzero dispatch exit
with a receipt means the candidate tests did not pass. A nonzero exit without a
receipt means no successful completion is established; inspect the claim and
infrastructure, then obtain a new approval before trying again.

## Remaining G4 gates

This slice does not dispatch a coding child, perform bounded correction, run the
required final creator/reviewer whole suite, or obtain independent critic/judge
review and creator acceptance. No production writing or final acceptance follows
from a passing candidate receipt. The applicable G3 quality gate remains separate.

# G4 isolated reviewer-test execution and count evidence

The third offline G4 slice executes one frozen reviewer-test package against one
exact implementation binding through the existing immutable-image, no-mount Docker
boundary. It retains a canonical receipt with observed test counts and validates a
paired known-good/known-bad control record. It does not authorize correction,
repository or VCS writes, network or credential access, provider dispatch, candidate
execution, or acceptance.

## Execution contract

`ReviewerTestExecutionRequest` binds an execution ID, one immutable implementation
binding hash, one exact `sha256:` container image ID, a role (`candidate`,
`known_good`, or `known_bad`) and a 5–60 second deadline. The product path has no
host-execution fallback. It revalidates the canonical frozen package and current
implementation tree before assembling the job and again after the container returns.

The self-contained job carries only the frozen reviewer package and the declared
implementation source/resource files. Dependency locks and build metadata remain
bound by hash, but runtime dependencies come from the named image. The worker creates
the adapter from the declarative direct-symbol allowlist; callers cannot supply
adapter code. A clean `python -I` child materializes inputs in private temporary
directories so an already imported installed package cannot shadow a bound package
with the same name.

The inherited `OfflineContainer` checks the local image identity and rejects implicit
image volumes. It uses no host mounts, disables networking, runs as a non-root user,
drops capabilities, enables no-new-privileges, makes the image root read-only, and
bounds memory, CPU, processes, file descriptors, temporary storage, input, output and
elapsed time. Container lifecycle records must be placed explicitly outside the
implementation and evidence paths. The launcher removes the exact container on
success, failure, timeout and cancellation.

## Counts and receipts

The isolated child uses the frozen `unittest discover` start directory, top-level
directory and pattern. Its observation records:

- collected, started, executed and skipped counts;
- failures, errors, expected failures and unexpected successes;
- ordered SHA-256 identities of collected, started and executed test IDs; and
- captured Python stdout/stderr bytes, capped at 64 KB.

Collected and started order must be identical, and the runtime collected/executed/
skipped counts must exactly equal the frozen collection contract. The worker hashes
the complete materialized inputs before and after execution; mutation or new input
files fail the worker. The host binds the observation to the exact canonical job and
writes a new private mode-`0600` receipt without overwriting an existing path.

For `candidate` and `known_good`, the role expectation requires exact counts and a
successful suite. For `known_bad`, it requires exact counts, at least one assertion
failure, zero errors and zero unexpected successes. An import, fixture,
infrastructure, timeout or other error is therefore not valid sensitivity evidence.

## Known controls

The control validator requires distinct execution IDs, implementation bindings and
implementation-tree hashes. Both receipts must use the same reviewer package,
adapter, image and collection contract, and must have identical collected, started
and executed test-ID digests. The known-good role must pass and the known-bad role
must fail by assertion as described above.

The resulting record proves only that this frozen package distinguished those two
bound fixtures under that image. It explicitly denies candidate execution and every
downstream authority. It does not prove that the fixtures are representative or that
a candidate is acceptable.

## Run and replay

Keep request, binding, package, implementation, output and lifecycle locations
separate. Then run:

```sh
uv run --frozen mos g4-run-reviewer-tests-isolated \
  --request execution-request.json \
  --binding immutable-implementation-binding.json \
  --reviewer-package frozen-reviewer-package.json \
  --implementation-root clean-implementation-tree \
  --docker /absolute/path/to/docker \
  --output execution-receipt.json \
  --lifecycle-root /private/path/container-lifecycles
```

Replay the retained evidence against current inputs:

```sh
uv run --frozen mos g4-verify-reviewer-test-execution \
  --receipt execution-receipt.json \
  --request execution-request.json \
  --binding immutable-implementation-binding.json \
  --reviewer-package frozen-reviewer-package.json \
  --implementation-root clean-implementation-tree
```

After independently running the known-good and known-bad bindings, validate and
replay their paired record:

```sh
uv run --frozen mos g4-validate-reviewer-test-controls \
  --known-good known-good-receipt.json \
  --known-bad known-bad-receipt.json \
  --output known-controls.json

uv run --frozen mos g4-verify-reviewer-test-controls \
  --control-record known-controls.json
```

## Remaining limits

Docker, the exact image and the host kernel remain trusted. Arbitrary Python inside a
run can alter process state, so byte/count evidence is not a semantic proof. The
separate authenticated-provenance slice now connects the source revision and tree to
trusted read-only Git, authenticated reviewer/creator custody and bounded E2 lineage.
It still does not prove that dependency declarations correspond to the image.
Candidate dispatch approval, bounded correction, final whole-suite execution and
independent critic/judge review remain later G4 work.

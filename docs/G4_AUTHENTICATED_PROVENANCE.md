# G4 authenticated custody and trusted VCS/E2 provenance

The fourth offline G4 slice authenticates the exact creator approval, blind
reviewer-package custody, bounded child assignment/result, read-only Git
reconstruction and existing known-control evidence in one immutable record. It
closes the authenticated-custody and trusted VCS/E2 provenance prerequisites; it
does not dispatch a child, execute a candidate, change Git, authorize correction or
accept an implementation.

## Signed custody and E2 lineage

`G4ProvenanceTrustPolicy` enrolls Ed25519 keys for creator, reviewer, VCS broker and
child roles. Schema 1 requires the three human roles to use distinct identities and
keys. Under ADR-0005, schema 2 may use one creator/reviewer/VCS operator only when the
custody record explicitly denies independent human review and accepts self-review
risk. Every child remains distinct from every human role and from every other child.

Domain-separated signatures bind these canonical artifacts in order:

1. the creator's exact plan, test-suite, public-interface, rubric and base-revision
   approval;
2. the reviewer's exact frozen package and the exact signed creator artifact;
3. the creator's bounded child assignment, declared complete creator-test paths,
   disjoint owned implementation paths and resource ceilings; and
4. the selected child's exact base/child revisions, full-index binary patch identity,
   changed paths and verification-evidence identity.

Timestamps must be UTC, fall inside the policy window and be monotonic. They are
signed local claims, not trusted third-party timestamps. A signature proves control
of an enrolled key over exact bytes; it does not prove a person's physical identity,
honest judgment or secure key storage.

## Trusted read-only Git reconstruction

The recorder accepts an absolute executable path, verifies its regular executable
file identity, and runs fixed Git argv without a shell. It supplies a minimal
environment with no inherited `HOME` or `PATH`, disables prompts, optional locks,
replacement objects, pagers, hooks, external diff/attributes, fsmonitor and
untracked-cache behavior, and grants no Git-write command.

Against the exact current `HEAD`, the recorder verifies:

- the binding's full source revision and implementation tree from committed Git
  objects, including every bound blob, mode, size and digest;
- a complete committed inventory beneath the bound implementation root;
- base → child → final-source ancestry, with three distinct commits;
- the child's exact full-index binary patch, byte count and changed-path set;
- every child change is within the signed owned paths and outside the signed creator
  test paths; and
- all bound worktree paths are clean, including untracked files.

`HEAD` is checked again after object reconstruction. The Git executable, repository
objects, OS and same-UID filesystem remain trusted; a same-UID actor that can race
and restore state is outside this offline boundary.

## Record, sign, assemble and replay

All evidence inputs and recorder output must remain outside the repository. First
produce the unsigned, canonical Git claim:

```sh
uv run --frozen mos g4-record-reviewer-git-provenance \
  --policy policy.json \
  --creator-approval signed-creator.json \
  --reviewer-custody signed-reviewer.json \
  --child-assignment signed-assignment.json \
  --child-result signed-result.json \
  --binding immutable-implementation-binding.json \
  --reviewer-package frozen-reviewer-package.json \
  --repository-root /absolute/repository \
  --implementation-root /absolute/repository \
  --git /absolute/path/to/git \
  --repository-id project-id \
  --output git-provenance.json
```

An external enrolled VCS signer signs the exact canonical `TrustedGitProvenance`
using the `mos-eisley/g4-git-provenance/v1` domain and stores a
`SignedTrustedGitProvenance`. Production commands intentionally accept no private
key. Assemble the signed evidence and known controls:

```sh
uv run --frozen mos g4-assemble-reviewer-provenance \
  --policy policy.json \
  --creator-approval signed-creator.json \
  --reviewer-custody signed-reviewer.json \
  --child-assignment signed-assignment.json \
  --child-result signed-result.json \
  --binding immutable-implementation-binding.json \
  --reviewer-package frozen-reviewer-package.json \
  --git-provenance signed-git-provenance.json \
  --controls known-controls.json \
  --output authenticated-provenance.json
```

Replay verifies every embedded signature and current input, then reconstructs the
current repository again:

```sh
uv run --frozen mos g4-verify-reviewer-provenance \
  --record authenticated-provenance.json \
  --binding immutable-implementation-binding.json \
  --reviewer-package frozen-reviewer-package.json \
  --controls known-controls.json \
  --repository-root /absolute/repository \
  --implementation-root /absolute/repository \
  --git /absolute/path/to/git
```

Outputs are private mode-`0600`, canonical, bounded and never overwritten. These
commands make no network or provider call.

## Remaining G4 work

The record proves an authenticated, internally consistent evidence chain under its
stated trust assumptions. The signed claim that the creator-test inventory is
complete and that the child subtask is meaningful still requires accountable human
review. Dependency declarations are not proof that the execution image contains the
same dependencies. Candidate dispatch, bounded correction, final whole-suite
execution and independent critic/judge acceptance remain separate G4 gates.

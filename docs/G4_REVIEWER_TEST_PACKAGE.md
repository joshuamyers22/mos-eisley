# G4 blind reviewer-test-package freezer

The first offline G4 slice freezes reviewer-derived tests before implementation or
author telemetry is revealed. It produces one canonical, content-addressed artifact
containing every declared test, fixture, input, expected value, parameter, oracle
and collection-config file plus the complete collection contract.

This boundary is deliberately inert. It does not execute tests, inspect or bind an
implementation, write a repository, use Git, access credentials or the network,
dispatch a provider, authorize correction, or accept a result. Each of those fields
is literally `false` in the manifest or frozen package. The separately reviewed
[allowlisted implementation binding](G4_IMPLEMENTATION_BINDING.md) is now implemented
as another inert artifact. Later G4 slices must still provide the isolated execution
broker, observed count checks, known-good/known-bad controls, correction bounds and
final review.

## Manifest contract

`ReviewerTestPackageManifest` requires:

- one content-addressed approved-plan reference;
- one or more content-addressed public-interface references;
- one rubric reference and one creator-approval reference;
- unique, sorted declarations for every package file;
- a fixed `unittest discover` start directory, filename pattern, top-level directory
  and positive collected/executed counts;
- one separate marker-approval reference for each declared skip/xfail marker; and
- literal denial of implementation inspection and every downstream authority.

References are supplied in the manifest's canonical `(kind, reference_id)` order.
The freezer checks their exact byte length and SHA-256 digest, but stores their
identities rather than their contents. That proves which inputs were named; it does
not authenticate the person who produced them. A later trust gate must validate the
creator/reviewer authority appropriate to the campaign.

All test files must be selected by the collection rule. At least one test must be
expected to execute, so an all-skipped package cannot be frozen. Expected collected,
executed and skipped counts are commitments for the later execution receipt; the
freezer does not claim that static inspection proves those runtime values.

## Freeze and replay verification

Create the manifest and package tree in a reviewer-owned location separate from the
implementation, then run:

```sh
uv run --frozen mos g4-freeze-reviewer-test-package \
  --manifest reviewer-manifest.json \
  --package-root reviewer-package \
  --reference approved-plan.md \
  --reference creator-approval.json \
  --reference public-interface.md \
  --reference rubric.md \
  --output frozen-reviewer-package.json
```

Repeat `--reference` once for every manifest reference in its exact order. The
command rejects overlap between the package root, reference inputs, manifest and
output. It reads only bounded regular files through no-follow directory traversal,
rejects hard links, duplicate inode aliases, symlinks, special files, path traversal,
byte drift, malformed Python and duplicate JSON keys, then writes a new mode-0600
artifact without overwriting an existing path.

Replay verification revalidates the embedded bytes, declarations, payload digest,
marker inventory and complete artifact hash without extracting or executing code:

```sh
uv run --frozen mos g4-verify-reviewer-test-package \
  --package frozen-reviewer-package.json
```

The emitted hashes are evidence identifiers, not execution or acceptance tokens.

## Marker and blindness limits

The freezer inventories common syntactic `unittest` and `pytest` skip/xfail forms as
a defense-in-depth check. Because arbitrary Python can construct equivalent behavior
dynamically, static inspection cannot prove the absence or semantics of every skip,
wrapper or oracle. Exact package bytes remain frozen, and the later isolated runner
must compare observed collected/executed/skipped counts with this contract and fail
closed on any difference.

Likewise, literal `implementation_inspected=false` and the absence of implementation
inputs make the intended blind handoff explicit, but a self-description cannot prove
a reviewer's mental independence. The derivation ceremony and its authenticated
evidence remain a separate G4 responsibility.

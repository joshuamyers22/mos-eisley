# G3 bounded execution-view qualification: four public candidates

- Date: 2026-09-28 UTC
- Source/method decision owner: Joshua Myers
- Result: **one bounded offline execution view passes the candidate controls; three do not**
- Authority: preproduction source qualification only; **zero G3 enrolled cases**

## Scope and decision rule

This audit follows the [frozen 12-row inspection frame](G3_SWE_REBENCH_CANDIDATE_FRAME.md)
and its four issue-only packets. It checks the **entire observable execution
view** for those four candidates: the pinned base tree, the projected task
workspace, the container mount and tool surface, and the declared whole-suite
test oracle. A passing view is a controlled candidate for Joshua's later
source/method review. It grants no sampling, label, arm, holdout, cost, or
production-outcome authority.

The decision rule was a reproducible base/test failure, gold/test success,
wrong-repair/test failure, every published fail-to-pass ID in the expected
state, every pass-to-pass ID passing, no other failing tests, and an
independent parser that rejects absent, malformed, repeated, or conflicting
terminal evidence. All runs used the source's full `go test -v ./...` scope
with Go's structured `-json` output. An issue-specific test passing while the
whole suite fails does **not** pass this rule. Public benchmark results remain
[preproduction evidence](PRODUCTION_OUTCOME_ACCEPTANCE.md).

## Pinned inputs and model-visible boundary

The [published Parquet](https://huggingface.co/datasets/nebius/SWE-rebench-V2/blob/475dd5e8703bb5fb22dd3c60b5d038b019eba1e0/data/train-00000-of-00001.parquet)
was rechecked at 428,839,266 bytes and SHA-256
`0e0bf9355f892ad74ae98d4e1c404f39fd6654a8e351ee3e6ab162e4a64cd3ad`.
For each candidate, the [workspace verifier](../tools/g3_execution_view_audit.py)
checks the packet's two-key allowlist and hash, GitHub's pinned commit and
recursive root-tree objects, every Git directory-tree hash, every archive
blob's Git SHA-1, file modes, archive bounds, and the exact generated workspace
file set. It rejects links, submodules, Git metadata and extra files. The
source tree, gold/test diffs and raw oracle logs stay in operator-only
temporary storage. The task-specific model material consists of **only** the
issue text in its opaque packet and the corresponding filtered base workspace
mounted over the image's original project path. The pinned image also exposes
its toolchain and dependencies; the runtime surface is addressed below and in
the threat model. No model was run in this audit.

| Packet / source | Git root tree | Source files → view files | View exclusion | Base archive SHA-256 |
|---|---|---:|---|---|
| 001 / `rsteube__carapace-273` | `6f95b1c24e1fe62c91d678e5847ac36f776b1247` | 113 → 113 | None | `af7178c4248dce3ad44942f9e6399f986a182a8e992734e202ec938d47f08a59` |
| 002 / `palantir__policy-bot-220` | `7ac854c8d2296d9e009be283bcdff73a974ca726` | 823 → 113 | 709 vendored files and one example config containing a PEM block | `02630a4b8fa455f9126f4428d1a716f0e5c0f6016fadaa8c172e06627f1d0906` |
| 003 / `google__osv-scanner-16` | `58a36a89f305a131a4257b7bc4e66761142ca8dc` | 193 → 193 | None | `a67980c38a8d5322aaa2ccf143c3d0d53a66c627cb94eb21d68cdccb84590245` |
| 004 / `mgechev__revive-665` | `33bb02da39578c96b7582402dee948bb720aba77` | 299 → 298 | Encrypted `.docs-deploy-key.pem.enc` | `a0b32e97ec91be61f52c3b445d217f89634441cd2ad27b778bcea648fc210a62` |

The filtered workspace digests bind the sorted relative path, Git mode and
file SHA-256 for every visible file, with a length prefix on each path:

| Packet | Filtered workspace SHA-256 |
|---|---|
| 001 | `ae83cd1e4071803b619162f4d0671b29365353e4c56e8df1eb0768c4a2b4e69b` |
| 002 | `d258775555bb6e9f3be6a0ea75dd7982a407a75ded560a1b1efe82801ebfe7cb` |
| 003 | `1f8d3d5f30ee828869a11b9b4278c60eae4719a775d066db1bde7efb68801082` |
| 004 | `ecc46901586ff75dc68db3deb9bb55fbf299afaa0c35d9ea1a7bc9f7be996d65` |

The verified base repositories carry the [Apache-2.0 or MIT license files at
their pinned commits](G3_SWE_REBENCH_CANDIDATE_FRAME.md#original-issues-rights-and-packet-decisions).
The policy-bot builder's install recipe removes `vendor/`; the task view does
so as well, and excludes its PEM-bearing example config. The revive encrypted
deploy key is excluded. This establishes a named-license and exposure screen
for these projected files, **not legal clearance** for all upstream content,
third-party assets, or a later product distribution. Retain attribution and
obtain Joshua's rights disposition before any source admission.

The source's image tags and registry manifest digests used for controls were:

| Packet | Pinned image manifest digest | Observed Go |
|---|---|---|
| 001 | `sha256:be16c7d961cfe45c69e996a06404456f8e8e0462e8249ecce931c163f8b53b0e` | 1.18.1 |
| 002 | `sha256:b98dcd67a0d1b0a8ebb125bf423fe526b7a2221302af4fc6d5b3fe92ffb8b590` | 1.18.1 |
| 003 | `sha256:c50f0f1dc2f553db73ec92f66075684a471c0f7d5cb4e1b93b284fedde637699` | 1.18.1 |
| 004 | `sha256:60a71460bbf69e0995ee7d47f5d81634a344fd8bb043b91b503b6411fa4c1502` | 1.23.0 |

The source images embed repository `.git` directories, so the candidate view
**must** overmount each original project path with the verified snapshot.
The mounted views were checked to lack `.git`; policy-bot's mounted image was
also checked for other reachable `.git`, `gold.diff`, `test.diff`, and
`expected.json` paths. Future dispatch must preserve the exact digest,
overmount, no-network mode, read-only root, capability drop, process and
CPU/memory limits, and separation from operator diffs/logs. The oracle
controls ran with `--network none`, `--read-only`, 2 CPUs, 2 GiB, 256 process
limit, all capabilities dropped, no-new-privileges, and an executable
bounded temporary build directory. The workspace was writable only so Go
could run the public test patch; operator diffs were applied outside the
container before each run and were never mounted as separate files.

An exact added-line scan of the base workspaces found only existing generic
lines or related implementations: two carapace lines and one revive AST case
line also appear in their later code patches; no exact added lines of 20 or
more characters appeared in the policy-bot or osv-scanner base. This is a
bounded literal check, not a guarantee against semantic disclosure or a
model's prior knowledge of public code. A key/token signature screen of the
filtered views found no matching private-key PEM, GitHub token, AWS access-key
pattern, or future repair PR URL. The issue-only packet review and its shorter
revive reproduction overlap remain [recorded separately](G3_SWE_REBENCH_CANDIDATE_FRAME.md).

## Casewise oracle decisions

| Packet | Base / gold / wrong exit | Published F2P behavior | P2P and whole-suite finding | Decision for this exact offline view |
|---|---|---|---|---|
| 001 carapace | 1 / 1 / 1 | Targeted `TestElvish` and `TestZsh` fail at base and pass at gold in `example/cmd`, but same names are skipped in another package. | 14/18 P2P IDs pass; gold still has 57 other failing test names under the conservative parser. | **Fail.** Package-name conflicts and unrelated whole-suite failures prevent an unambiguous oracle. |
| 002 policy-bot | 1 / 0 / 1 | `TestParsePolicyError_recursiveDepth` fails / passes / fails. | 147/147 P2P IDs pass, zero other failures. `TestChangedFiles` occurs in two packages and passes in both. | **Pass as bounded preproduction execution view**, subject to the limits below. |
| 003 osv-scanner | 1 / 1 / 1 | Two child checks pass at gold, while parent `TestRun` remains failed. | 173/179 P2P IDs pass; six other subtests call the live OSV API and fail with network disabled. | **Fail.** The published whole-suite oracle depends on a live external service. |
| 004 revive | 1 / 1 / 1 | `TestNestedStructs` fails / passes / fails. | 113/113 P2P IDs pass, but nine other test names fail at gold. One shows a Go type-message mismatch. | **Fail.** The published image does not produce a clean gold whole suite. |

The policy-bot view passed **three fresh base/gold/wrong rounds** under the
same bounded container contract. Its listed P2P name `TestChangedFiles` occurs
in two packages. After the first round exposed that duplicate, the
[independent parser](../tools/g3_oracle_controls.py) was tightened to require
**every** terminal occurrence of a listed name to have the expected status,
to reject a conflicting or repeated `(package, test)` terminal, and to reject
other failures. The first round's unchanged JSON logs were replayed under
the tightened rule; rounds two and three used it before execution. This is a
disclosed calibration refinement, **not a retrospectively sealed G3
preregistration**. The parser also rejected a gold log with a required pass
event removed, a conflicting duplicate inserted, and a malformed JSON line.

The three failed cases are not silently repaired by narrowing the test
command, enabling a network service, ignoring P2P IDs, or relabeling a parent
test. A future changed oracle would be a new source-protocol version requiring
fresh controls and Joshua's review. The policy-bot pass shows only that this
published test oracle discriminates the selected repair under the declared
view. It does not prove every issue requirement, task independence, source
representativeness, absence of quality harm, or any comparative model result.

## Study boundary and next decision

The [verification record](G3_SWE_REBENCH_EXECUTION_VIEW_VERIFICATION.md)
contains reproduction steps, log digests, negative checks and the resource
account. The [threat review](G3_SWE_REBENCH_EXECUTION_VIEW_THREAT_MODEL.md)
records the remaining model/runtime boundary. The source frame still has
**four historical candidate IDs and zero eligible G3 cases**; these casewise
decisions do not alter its sampling status. Joshua must decide whether the
single passing source can enter a prospective candidate pool and must review
rights, historical exposure, dependence, the six-arm sample/spend design,
the single-human verifier amendment, and externally timestamped registration
before any label, assignment or outcome-bearing run. A single passing public
case cannot establish that pool's feasibility or a production outcome.

# Verification: four G3 public-case execution views

## Objective, authority and rubric

- Objective: decide whether each of four frozen public candidates has a reproducible, leakage-screened **complete offline task view and whole-suite oracle** suitable for further owner review.
- Starting revision: `2b272d6d8f04c36fc1278fdb2f71640acc3021c7`, clean worktree.
- Guidance selected: [Python engineering guide](PYTHON_ENGINEERING_GUIDE.md), [bounded verification guide](AGENTIC_VERIFICATION_GUIDE.md) and [loop template](../templates/AGENTIC_VERIFICATION_LOOP.md), [threat-model template](../templates/THREAT_MODEL.md), [work-note template](../templates/WORK_NOTE.md).
- Risk: high for source integrity, model leakage and false oracle claims. Joshua Myers is the accountable rights, source and method reviewer; agent checks are not approval.
- Invariants: do not access the sampling registry, custodian mapping, label store or outcome store; do not infer probabilities, groups, labels or splits; do not run models, providers or study arms; do not put task text, diffs, raw logs or outcomes in the source frame or a sampling artifact.
- Resource ceiling: four public base archives under 2.1 MB compressed total, one candidate image at a time, no provider or study spend; each test run had 2 CPUs, 2 GiB, 256 PIDs, no network and a 360-second timeout. Stop a case when the declared oracle fails; repeat only a passing candidate for stability.

| Gate | Blocking threshold | Evidence |
|---|---|---|
| Source identity and view | Full commit/tree/blob verification; packet allowlist; exact output file set; no Git metadata or excluded sensitive file | [Workspace tool](../tools/g3_execution_view_audit.py), archive and root-tree hashes in the [audit](G3_SWE_REBENCH_EXECUTION_VIEW_AUDIT.md) |
| Leakage and rights screen | No known credential signature or future PR URL; named base license and view exclusions reviewed | Tool's limited scan and [threat model](G3_SWE_REBENCH_EXECUTION_VIEW_THREAT_MODEL.md) |
| Oracle discrimination | Base fails, gold passes, wrong repair fails; all declared F2P/P2P statuses correct; no other failures | [Independent parser and control tool](../tools/g3_oracle_controls.py), pinned image and log hashes below |
| Parser failure behavior | Missing, malformed, conflicting or repeated terminal evidence fails closed | Mutated gold-log checks below |
| Study authority | No case promoted from this audit alone | ADR-0010, source frame and owner gate |

## Source and view reproduction

Input file: `/private/tmp/g3_swe_rebench_v2_475dd5e.parquet`; exact byte
count and SHA-256 are in the [audit](G3_SWE_REBENCH_EXECUTION_VIEW_AUDIT.md).
The local operator directory `/private/tmp/g3_execution_view_20260928`
contains `NAME.tar.gz`, `NAME.commit.json` and `NAME.root-tree.json` for names
`carapace`, `policy-bot`, `osv-scanner` and `revive`. The archives came from
GitHub's `codeload.github.com/OWNER/REPO/tar.gz/BASE` endpoints; commit and
recursive-tree JSON came from GitHub's `repos/OWNER/REPO/git/commits/BASE`
and `repos/OWNER/REPO/git/trees/ROOT_TREE?recursive=1` API endpoints. Exact
owners, bases, root trees and archive hashes are in the [frame](G3_SWE_REBENCH_CANDIDATE_FRAME.json)
and [audit](G3_SWE_REBENCH_EXECUTION_VIEW_AUDIT.md). The source's
[dataset card](https://huggingface.co/datasets/nebius/SWE-rebench-V2) and
[builder repository](https://github.com/SWE-rebench/SWE-rebench-V2/tree/c71902a8cf8d2b725f63d51f199f4d3e56f68d2d)
are the upstream publication references.

Rebuild or verify the four model task workspaces and operator patch files:

```sh
uvx --offline --from duckdb==1.5.5 python \
  tools/g3_execution_view_audit.py \
  /private/tmp/g3_swe_rebench_v2_475dd5e.parquet \
  /private/tmp/g3_execution_view_20260928 \
  /private/tmp/g3_execution_view_20260928
```

The tool reconstructed all four authentic Git root hashes and 1,428 file
blobs, then verified 711 exclusions and the exact remaining workspaces.
It produced no labels, groups, assignment, or sampling receipt. Its literal
overlap and known-key scans are bounded indicators; see the [threat model](G3_SWE_REBENCH_EXECUTION_VIEW_THREAT_MODEL.md).

**Negative tree mutation:** changing a directory entry SHA in a copied
carapace recursive-tree JSON originally escaped a blob-only check. The tool
was corrected to recompute each directory tree, and the same mutation then
raised `ValueError: recursive Git tree hash differs: <root>`. All four
unmodified sources passed after the correction. This is a concrete resolved
verifier defect, not evidence that GitHub signed the source.
Adding an otherwise empty `.git` directory to a copied generated workspace
also caused `ValueError: workspace file or directory set differs`; the
authentic workspaces still passed exact file and directory checks.

## Offline controls and independent parser

For each case, [the control tool](../tools/g3_oracle_controls.py) copied the
verified view into fresh base, gold and deliberately wrong no-op-repair
workspaces, applied the public test patch outside the container, and ran
`go test -json ./...` inside the **digest-pinned** source image. Only the
workspace was overmounted at the image's original project path; the gold
diff and test diff were not mounted as files. Container settings are in the
[audit](G3_SWE_REBENCH_EXECUTION_VIEW_AUDIT.md). The expected IDs came from
the pinned public row; the independent parser used Go JSON events and required
all occurrences of each listed name to agree on the expected terminal status.
[Go's command documentation](https://pkg.go.dev/cmd/go#hdr-Testing_flags)
states that `-json` presents the verbose test information in a machine-readable
form. Each round used fresh workspaces and a separate Go build cache.

Run shape, replacing packet, digest and mount from the [audit table](G3_SWE_REBENCH_EXECUTION_VIEW_AUDIT.md#pinned-inputs-and-model-visible-boundary):

```sh
uvx --offline --from duckdb==1.5.5 python tools/g3_oracle_controls.py \
  /private/tmp/g3_swe_rebench_v2_475dd5e.parquet \
  /private/tmp/g3_execution_view_20260928 \
  packet-002 \
  sha256:b98dcd67a0d1b0a8ebb125bf423fe526b7a2221302af4fc6d5b3fe92ffb8b590 \
  /policy-bot --round 2
```

The following SHA-256 values identify the operator-only JSON summaries in
`/private/tmp/g3_execution_view_20260928/controls`. Each summary contains
the exact stdout SHA-256, exit code and parser result for every base, gold and
wrong run. Raw logs remain outside Git and are **not** sampling artifacts.

| Case / round | Summary file | Summary SHA-256 | Result |
|---|---|---|---|
| 001 carapace, first valid container round | `packet-001/summary-rescore.json` | `2bc5167ad221ba19c559b991c57a47672a02d24a8c462a20fdd851146be0fbed` | Fail: gold whole suite and conflicting duplicate names |
| 002 policy-bot, round 1 reparsed | `packet-002/summary-rescore.json` | `cbb487365ddc7aa7a3fffcb3e4bff81d02ef30b3be1cd5d50b60ca08f6602364` | Pass: base 1, gold 0, wrong 1; 147/147 P2P |
| 002 policy-bot, round 2 | `packet-002-repeat2/summary.json` | `3d8ebc6cf650d434200c2abd0b12875eb0eb06ba9eb0069c16af92f2d9fba694` | Pass: same pattern |
| 002 policy-bot, round 3 | `packet-002-repeat3/summary.json` | `6b3da3db8b03f5177eb9d04507d91592039fb414a8b47e5a241f012d5def32c7` | Pass: same pattern |
| 003 osv-scanner | `packet-003/summary.json` | `c83e73e402e672223e547ffac431034e0c9b884e5b996c82c3459e96e21785ce` | Fail: live OSV API required by six tests |
| 004 revive | `packet-004/summary.json` | `8e6961606514bd3f456039dcfeb752c78a4b83ce09d57945ce339a9586139c79` | Fail: nine other tests fail at gold |

The first carapace container attempt used a non-executable `/tmp` mount;
all tests failed to launch with `permission denied`. Those logs were preserved
separately under `controls-noexec` and **not** counted as an oracle result.
The mount was corrected to `rw,exec,size=512m`, and the valid run above was
made from fresh copies. A server interruption also stopped an incomplete
first attempt at policy-bot round 3; its partial workspace/cache were moved
to `controls-interrupted`, and the complete third round was rerun fresh.

The first parser version rejected any repeated test name across packages.
Round 1 of policy-bot exposed two passing `TestChangedFiles` instances in
separate packages. A stricter semantic rule accepts a listed name only when
**all** package occurrences have the expected status; it rejects conflicting
statuses and duplicate terminal events for the same package/name. The old
logs were not changed; `--rescore-only` wrote separate summaries. Rounds 2
and 3 were executed with that parser already fixed. This refinement happened
in public preproduction calibration and cannot be presented as a preregistered
study rule. For every passing policy-bot gold run, deleting the required pass
event, adding a conflicting terminal event, or adding malformed JSON caused
the parser to reject the log.
After these runs, the runner's stdout/stderr handling was changed from
in-memory capture to file-backed capture to bound host memory. The Docker
command, parser and controls were unchanged; replaying the saved third-round
logs with the final parser reproduced the same pass statuses and hashes.

## Findings and disposition

| ID | Finding | Disposition |
|---|---|---|
| E-001 | Authentic source images embed `.git`; visible base directories could reveal history. | Exact workspace mount hides `.git`; future dispatcher must enforce it and deny Docker socket/network. |
| E-002 | Policy-bot base tree contains 709 vendor files and a PEM-bearing example config; revive contains an encrypted deploy key. | Exact workspace exclusions; authenticated source remains archived separately. Rights and credential-pattern residuals are in the threat model. |
| E-003 | Carapace and revive targeted tests discriminate, but their gold whole suites still fail; osv-scanner needs a live API. | Three candidates fail this oracle version. Do not narrow or relabel silently. |
| E-004 | Policy-bot duplicate P2P name was discovered during calibration. | Parser rule tightened, old logs reparsed, two new full rounds passed; disclose post hoc change and freeze a future method before enrollment. |
| E-005 | Initial verifier missed a changed Git directory entry. | Full tree-object reconstruction added; tampered manifest now rejected. |

No study source, cohort, oracle label, assignment, preregistration or
production-outcome claim is sealed. Joshua's accountable source/method review,
dependence and six-arm feasibility, rights disposition and single-human
verifier amendment remain open. The [production outcome contract](PRODUCTION_OUTCOME_ACCEPTANCE.md)
still requires actual real owner-task outcomes for production claims.

## Quality gate

The two new standalone tools were formatted and passed Ruff. The authentic
source/view rebuild, changed-tree rejection, extra `.git` directory rejection,
and final parser replay passed after the last tool edits. New Markdown local
links and `git diff --check` passed.

The required host-permitted `make check` was run once for the combined batch.
Ruff and Pyright passed. Its source suite ran **2,540 tests in 1,884.718
seconds**, with four skips and **one error** in
`test_review_launch_admission.LaunchAdmissionTests.test_cancellation_awaits_worker_cleanup_and_cannot_retry`:
`ValueError: verified critic quorum was not met`. This test is outside the
G3 source-audit tools. The exact test passed alone (1 test) and its whole
module passed (24 tests) immediately afterward. That pattern is consistent
with an intermittent broad-suite fixture failure, but does not prove its
cause. The `make check` command **failed** and did not reach coverage report,
build, or installed-wheel smoke; none is reported as passing for this batch.
The pushed PR's CI is the next broad rerun, and its outcome must be reviewed
before merge. No product runtime or launch-admission code was changed to mask
the failure.

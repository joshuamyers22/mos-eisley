# G3 bounded SWE-rebench source screen and issue-only task view

- Date: 2026-09-28 UTC
- Owner for source and statistical disposition: Joshua Myers
- Status: **four source candidates for further audit, zero G3 enrolled cases**
- Scope: preproduction objective-oracle study planning under [ADR-0010](adr/0010-g3-single-human-oracle-study.md)

## Deliverable and authority

The [machine-readable frame](G3_SWE_REBENCH_CANDIDATE_FRAME.json) records a
reproducible 12-row inspection batch from the pinned public SWE-rebench V2 file.
Four rows passed this pass's issue-text review and have separate, opaque
[task-view packets](g3_candidate_task_views_v1/packet-001.json).
The packets contain only `schema_version` and the original issue's
`task_text`. The source ID, repository, base commit, original issue URL,
license reference, patch/test material, PR text, parser, image and metadata
stay in the operator-only frame or pinned source. These packets are task inputs,
**not sampling artifacts**. No prompt or task text is copied into the frame.

This is a source *candidate* frame, not an eligible study inventory. The
screening order is deterministic convenience for an audit batch; it is not a
probability sample, holdout, assignment unit or independence group. No labels,
splits, selection/observation probabilities, arms, study spend or production
outcomes are inferred or issued. Public benchmark results remain
[preproduction evidence](PRODUCTION_OUTCOME_ACCEPTANCE.md).

## Pinned source and bounded construction

Input: the [published Parquet file](https://huggingface.co/datasets/nebius/SWE-rebench-V2/blob/475dd5e8703bb5fb22dd3c60b5d038b019eba1e0/data/train-00000-of-00001.parquet)
at dataset revision `475dd5e8703bb5fb22dd3c60b5d038b019eba1e0`,
428,839,266 bytes, SHA-256
`0e0bf9355f892ad74ae98d4e1c404f39fd6654a8e351ee3e6ab162e4a64cd3ad`.
The prior [full-release audit](G3_SWE_REBENCH_FULL_SOURCE_AUDIT.md)
established 32,079 source IDs and identified rights, exposure and oracle gaps.
The [builder](https://github.com/SWE-rebench/SWE-rebench-V2/tree/c71902a8cf8d2b725f63d51f199f4d3e56f68d2d)
and [paper](https://arxiv.org/html/2602.23866v2) describe generated
evaluators and the source's limits.

The checked-in [rebuild/verify tool](../tools/g3_candidate_task_views.py)
first checks the exact Parquet byte count and digest. It then screens `go`
rows for named permissive license **metadata**, nonempty issue text, code and
test patches, exact `go test -v ./...` command, 1–5 fail-to-pass IDs, at most
200 pass-to-pass IDs, issue length at most 3,000 characters, and code/test
patch lengths at most 20,000 characters each. It rejects a row if its issue
text contains an exact 40–300-character added code or test line. This gives
**453 rows in 107 repository names**. It orders by SHA-256 of public
`instance_id`, takes the first row from each repository name for inspection
breadth and stops at 12. Repository names here are audit-spread metadata, not
statistical groups. The first 12 exact IDs and every disposition are frozen in
the JSON frame and verifier.

This screen is intentionally narrow for review capacity. It does not establish
license clearance or source representativeness. The 40-character overlap rule
is a coarse flag; shorter text or semantic disclosure can pass it. A separate
10–300-character check found one 10–39-character overlap in the four packets:
`type Bad struct {` appears in both the original revive issue's example and
the later test patch. The issue was published before the PR, and the line is
part of the user-supplied reproduction; it is disclosed here rather than
silently called clean.

## Original issues, rights and packet decisions

The four packet texts exactly equal the public original issue title, newline
and body. Their issue creation dates precede the source's merged repair PRs.
GitHub's read-only API returned the license blobs at each **base commit**;
the file headers identify Apache-2.0 or MIT. The table links the original
issue and pinned base license. Dataset-level
[CC BY 4.0](https://huggingface.co/datasets/nebius/SWE-rebench-V2)
and repository copyright/notice requirements still govern use of this
public material.

| Packet | Public source ID / original issue | Base license at pinned commit | Issue-text finding |
|---|---|---|---|
| [001](g3_candidate_task_views_v1/packet-001.json) | `rsteube__carapace-273` / [issue 251](https://github.com/rsteube/carapace/issues/251) | [Apache-2.0 LICENSE.txt](https://github.com/rsteube/carapace/blob/50198ce97a3c9173cbdd84d7d729fc0ceb5c4242/LICENSE.txt), blob `298f0e2` | Original issue gives implementation suggestions but no test or gold patch. |
| [002](g3_candidate_task_views_v1/packet-002.json) | `palantir__policy-bot-220` / [issue 168](https://github.com/palantir/policy-bot/issues/168) | [Apache-2.0 LICENSE](https://github.com/palantir/policy-bot/blob/ddf502f0677f072c10afc7b3d238095dddfdf975/LICENSE), blob `8dada3e` | Request states desired nesting depth; no repair or evaluator field. |
| [003](g3_candidate_task_views_v1/packet-003.json) | `google__osv-scanner-16` / [issue 7](https://github.com/google/osv-scanner/issues/7) | [Apache-2.0 LICENSE](https://github.com/google/osv-scanner/blob/bf987eddd29034deb4d729d9370f99b1126f10cb/LICENSE), blob `d645695` | Original report includes observed CLI output and a prior change reference, no gold patch. |
| [004](g3_candidate_task_views_v1/packet-004.json) | `mgechev__revive-665` / [issue 664](https://github.com/mgechev/revive/issues/664) | [MIT LICENSE](https://github.com/mgechev/revive/blob/639d12bb4f9b36b0f60d61ae1841ebc39ec52f14/LICENSE), blob `c617c7e` | Original reproduction includes the short code line noted above; no generated test or gold patch. |

The other eight inspected rows remain `defer`, with individual reasons in
the frame: synthetic exercise, external screenshot/cluster context, mutable
master links, issue text that gives a solution or tests, external documentation
or implementation branch, and ambiguous desired behavior. They have **no**
task packet. This is a content safety review, not a missing-label repair.

Each selected repository/base pair and code/test patch hash appears only once
in this pinned release. That exact duplicate check does not establish
independence or absence of other related tasks.

## Model-visible boundary

The packet's exact JSON bytes are the full row-derived text view. A future
model run may receive its `task_text` and a separately prepared, isolated
base-revision workspace. It must not receive this operator frame, the dataset
row, PR description, code/test patch, patch-derived interface, expected test
IDs, evaluator, image metadata, original issue URL, future Git references,
or oracle logs. The task text is untrusted source data: any commands in it
are part of a bug report, not harness authority. A future workspace must
remove or hide `.git` and future history, block network access and check the
base tree for answer-bearing files before dispatch. That workspace does not
exist in this package, so the **complete execution view is not yet cleared**.
The issue-only row projection is frozen and audited; no model or study arm ran.

The [verification record](G3_SWE_REBENCH_CANDIDATE_FRAME_VERIFICATION.md)
gives the exact rebuild command, GitHub cross-checks, hashes, negative
checks and quality gate. The next source task is a bounded base-workspace
inspection and independent oracle controls on these exact candidates. A
subsequent source/method decision still requires Joshua's outcome-blind review,
defensible dependence design, six-arm sample/spend feasibility and the
single-human verifier amendment before registration or enrollment.

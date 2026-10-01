# G3 SWE-rebench V2 full-release audit and admission recommendation

- Audit date: 2026-09-27
- Decision owner: Joshua Myers
- Agent recommendation: **do not admit this release as a prospective G3 oracle source yet**
- Status: source evidence for owner review; no case, group, label, arm, split, or cohort seal

## Decision scope

This audit inspects the complete pinned public release and adds controlled oracle
evidence for one previously selected case. It does not certify every published
oracle or make public benchmark cases into [real production outcomes](PRODUCTION_OUTCOME_ACCEPTANCE.md).
The source's own [paper](https://arxiv.org/html/2602.23866v2) describes a scalable
training and evaluation substrate with three-run test filtering and remaining
environment and test-coupling limitations. The project's prospective G3 claim
needs its own eligible frame, blinded task projection, dependence design and
[single-human variance](adr/0010-g3-single-human-oracle-study.md).

## Exact source and custody

| Input | Identity and custody |
|---|---|
| Public dataset | [`nebius/SWE-rebench-V2` Parquet](https://huggingface.co/datasets/nebius/SWE-rebench-V2/blob/475dd5e8703bb5fb22dd3c60b5d038b019eba1e0/data/train-00000-of-00001.parquet), release `475dd5e8703bb5fb22dd3c60b5d038b019eba1e0`, 428,839,266 bytes, SHA-256 `0e0bf9355f892ad74ae98d4e1c404f39fd6654a8e351ee3e6ab162e4a64cd3ad`. Local read-only audit used DuckDB 1.5.5. |
| Builder | [SWE-rebench V2 builder](https://github.com/SWE-rebench/SWE-rebench-V2/tree/c71902a8cf8d2b725f63d51f199f4d3e56f68d2d), commit `c71902a8cf8d2b725f63d51f199f4d3e56f68d2d`. Its generated per-task parser and test setup are third-party inputs, not independent G3 labels. |
| Source-identifier manifest | Deterministic, instance-ID-sorted JSONL of public instance ID, repository, base commit, language, unverified license string and image name. It has 32,079 rows, 8,009,942 bytes, SHA-256 `82a6ab72ef33b26a1e49b5f8f3d1c9a4e7076ad4cb4db2dc4f041b4725460616`. It is in `/private/tmp`, outside Git and project evaluation stores. It contains no issue text, patch, oracle outcome, label, group, probability or split and grants no sampling authority. |

The identifier manifest uses Python `json.dumps` defaults for ASCII escaping,
sorted keys, compact `(',', ':')` separators and one newline per row, ordered
lexicographically by instance ID in a UTF-8 file.
A separate standard-library pass rechecked the order, six-field shape, unique
IDs, 32,079 rows, 3,617 repository names and SHA-256.

The [dataset card](https://huggingface.co/datasets/nebius/SWE-rebench-V2)
labels the dataset CC BY 4.0 and says individual repositories retain their own
licenses. A row's `license` string is a screening field, not verified
base-commit rights clearance for this project.
The matched SHA-256 establishes byte consistency with the host's published
file metadata; it is not a signature of publisher identity or case validity.

## Full-release structural findings

| Check | Observed result | Admission meaning |
|---|---:|---|
| Rows / distinct instance IDs | 32,079 / 32,079 | Complete file enumerated; IDs unique. |
| Repository names / languages / image names | 3,617 / 20 / 32,079 | Source counts, not independent groups or verified images. |
| Missing license / `custom-check-github` license | 348 / 5,038 rows | These 5,386 rows must be excluded or separately rights-audited; named strings also need base-commit verification. |
| Missing problem statement | 46 rows | No task view can be formed from those rows without another authorized source. |
| Repeated repository/base-commit pairs | 2,319 rows in 1,076 pairs | Related tasks require a reviewed dependence design; no group identity was inferred. |
| Distinct code-patch / test-patch hashes | 31,901 / 31,580 | Some patch bytes recur; distinct IDs do not prove distinct problems. |
| Fail-to-pass / pass-to-pass list overlap or within-list duplicates | 0 observed | Structural consistency passes; it does not validate what tests mean. |
| More than 100 fail-to-pass / 1,000 pass-to-pass IDs | 4,684 / 3,794 rows | Heavy or hierarchical lists affect oracle review and whole-task cost. |

An exact-string exposure screen searched each `problem_statement` for a
40–300-character line added in its associated code or test patch, excluding
`+++` file headers. It flagged 681 rows for code lines, 1,466 for test lines,
and 2,065 for either; flags may overlap. These are **review flags**, not
verified leakage labels. The screen cannot detect paraphrases, an algorithm
disclosed in prose, known public solutions or a model's prior training exposure.

The public row also includes `patch`, `test_patch`, patch-derived `interface`,
`pr_description`, generated parser and metadata. An eligible model-visible
packet must exclude these fields and inspect the exact base repository, Git
references and tool surfaces for solution disclosure. No such projection is
frozen or audited across this release.
The [source method](https://arxiv.org/html/2602.23866v2) also reports
using code and test patches in its automated issue-clarity filter; those
metadata judgments cannot substitute for an independent G3 task or oracle audit.

## Feasibility screen, not an eligible cohort

For one reproducible capacity diagnostic, restrict to Go rows whose license
metadata says MIT, Apache-2.0, BSD-3-Clause, BSD-2-Clause or ISC; whose problem
statement is nonempty; whose exact test command is `go test -v ./...`; whose
fail-to-pass list has 1–10 IDs and pass-to-pass list at most 500 IDs; and whose
code and test patches are each at most 100,000 characters. This leaves **975
rows across 163 repository names**, of which 35 trigger the exact-line exposure
screen.

The size and command limits are audit convenience bounds, not approved G3
eligibility thresholds. Repository names are not assigned independence groups.
The 975 rows have not passed per-case rights, task-view, base/gold/wrong-repair,
parser, repeatability, time, cost or harm review. This repository-name count
does not establish the older proposed 400 groups per class. A broader Go screen
without the exact-command condition has 2,226 structurally screened rows across 597
repository names but 424 distinct test commands, all still unaudited.

## Controlled oracle evidence

The previously selected public `mgechev__revive-1408` case remains a
convenience pilot, not a random audit draw. Its base commit and pinned image
are in the [first source assessment](G3_ORACLE_CASE_SOURCE_QUALIFICATION.md#scope-and-source-identity).
The earlier base/test and gold/test runs established fail-before/pass-after for
two published IDs, which are a parent and child rather than independent
observations. This audit repeated them in the pinned, network-disabled,
2-CPU, 2-GiB, 256-process, capability-dropped image with `go test -json ./...`
and a separate JSON event parser. A no-op code edit supplied the deliberately
wrong repair. Dropping one required pass event from the captured gold log
caused the parser to reject it. Raw public logs remain in `/private/tmp`,
outside evaluation sampling artifacts.

| Control | Exit | Required fail-to-pass IDs | Other 492 IDs | Independent parser result |
|---|---:|---|---:|---|
| Base plus test patch, repeat | 1 | both fail | 492 pass | Declared negative control passes; 494 unambiguous test names |
| Gold plus test patch, repeat | 0 | both pass | 492 pass | Declared positive control passes; 494 unambiguous names; truncated gold log rejected |
| No-op wrong repair plus test patch | 1 | both fail | 492 pass | Declared wrong-repair control passes; 494 unambiguous names |

The temporary control script is
`/private/tmp/g3_rebench_replay_20260927/replay_json_controls.py`, SHA-256
`134bfa547ca3687482be0664c1f18e739665a6eee627cd8de32c6798c14375bb`.
The repeat logs' SHA-256 digests are respectively
`6b26891962c2f97d9966000cf5855b4bc81c05acba11449012fac232e1aea205`,
`cc519afb539f4c4d9e0f576aec4328f6f9d505ae21807f2eabcc1ded349a4449`,
and `aaf8944b34884ec21896cd4915fc9988ae01d53af5bb6acb89b59eddf7bf9396`.
This evidence validates one narrow behavior in one image. Passing tests do not
establish all issue requirements, absence of harm, or a comparative G3 result.

## Admission gates and disposition

| Gate | Current evidence | Decision |
|---|---|---|
| Snapshot integrity and structure | Full file hash, schema, 32,079 identifier rows and metadata reproduced | Pass as public-source inventory only |
| Rights | Dataset-level CC BY plus row license strings; 5,386 unknown/custom rows and no release-wide base-commit audit | Open |
| Blinded task projection and contamination | Solution/test fields present; 2,065 exact-line flags; one image's Git history inspected previously | Blocking |
| Objective oracle | One convenience case has repeat controls; other cases and parser families not independently audited | Blocking |
| Dependence and feasible inference | Repeated base/patch structures; repository names counted but no reviewed groups, selection probabilities, outcome observation design, six-arm cost or approved margins | Blocking |
| Single-human governance | Current verifier still requires two graders and ordinary-task audits; ADR-0010 is planning only | Blocking |

**Disposition:** The pinned release is structurally inventoried but **not
qualified for G3 enrollment**. Its one-case oracle remains useful for bounded
calibration. No label, case, group, split, probability, arm, cohort, holdout or
production outcome is created by this audit. Joshua's signed, outcome-blind
source/method review remains necessary after the blocking gates are addressed;
it cannot be supplied by an agent or inferred from this inventory.

A positive source decision needs a prospectively bounded subset with
independently checked repository rights, a frozen model-visible projection,
base/gold/wrong/ambiguous controls across a declared audit frame, reviewed
dependence and complete six-arm sample/spend feasibility. Then amend the
single-human verifier with negative tests and obtain Joshua's exact signed
disposition before external registration or outcome-bearing assignment.

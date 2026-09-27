# G3 oracle-backed case-source qualification

- Date: 2026-09-27
- Decision owner: Joshua Myers
- Assessment status: evidence record for owner review; no source or cohort seal

## Decision

**SWE-rebench V2 is a promising source candidate, but it is not qualified for the
prospective G3 cohort.** One pinned public Go case has a locally reproduced,
discriminating fail-before/pass-after test oracle. That supports a future
controlled *pilot calibration* of the oracle workflow, subject to ordinary
execution authorization. It is not evidence
that the other 32,078 published tasks have valid G3 labels, distinct independent
groups, a leakage-safe task view, usable sampling probabilities, or the proposed
study's cost and harm coverage. No case was enrolled, labeled, signed, split, or
registered by this assessment.
Under the later [production outcome acceptance contract](PRODUCTION_OUTCOME_ACCEPTANCE.md),
even a fully validated public case source would remain preproduction evidence.
Running such a case in a production environment would not turn its test result
into a real owner's task outcome or authorize a production improvement claim.

NIST Juliet C/C++ 1.3 remains a [conditional flaw-detection candidate](G3_JULIET_SOURCE_AUDIT.md),
not a G3 source. A follow-up local check compiled one public CWE190 `_01` file
with Clang UBSan and observed the bad path fault on `2147483647` while its two
good paths did not fault on that input. This validates only that executable
example. The archive lists 90 CWE190 and 69 CWE191 `_01` baseline files; even
if each were a distinct family, that 159-stem restricted pool would fall short
of the earlier proposed 400 groups per class. Those stems were not audited as
independence groups. Many Juliet cases have no reliable runtime signal, and its
answer cues remain a separate eligibility failure. The earlier 400-group design
is itself a proposal under [ADR-0010](adr/0010-g3-single-human-oracle-study.md),
not an approved threshold to carry forward.

## Scope and source identity

| Item | Pinned or observed evidence | Qualification meaning |
|---|---|---|
| Full SWE-rebench V2 release | Hugging Face `nebius/SWE-rebench-V2` HEAD observed as `475dd5e8703bb5fb22dd3c60b5d038b019eba1e0` on 2026-09-27. The [dataset card](https://huggingface.co/datasets/nebius/SWE-rebench-V2/blob/main/README.md) reports 32,079 tasks and a CC BY 4.0 dataset license, with per-repository license fields. Full data were not downloaded or enumerated here. | Published scale and license are candidate-level facts, not an eligible inventory or redistribution clearance for any selected repository. |
| Source method | [Paper v2](https://arxiv.org/html/2602.23866v2) reports 32,079 issue-linked executable tasks from 3,617 repositories, at least one fail-to-pass test per retained task, and three stable validation runs. It also documents test coupling, external-dependency and environment limitations. | Source claims support screening; they are not independent G3 oracle certification. Repository count is not an independence-group count. |
| Builder | [Official builder](https://github.com/SWE-rebench/SWE-rebench-V2) commit `c71902a8cf8d2b725f63d51f199f4d3e56f68d2d`. `scripts/eval.py` applies both code and test patches before running the task's test command and parsing output. | The evaluation mechanism is inspectable; its generated parser and expected test IDs still require case-level validation. |
| Public sample | [20-task sample](https://huggingface.co/datasets/ibragim-bad/SWE-rebench-V2-sample) commit `9a7cd16b2431fc9f0abaf4c359e21fd3fae12ae3`; Parquet file 369,984 bytes, SHA-256 `db780c904275b75730a94e2697695cd2dda66fa9a560c61bea0340f97493144f`. | A screening sample only. It is not the full eligible frame; this sample lacks the full dataset's per-row `license` field. |
| Replayed case | `mgechev__revive-1408`, base commit `24c008dd000c009c35867463b25497be939275d3`, prebuilt image `docker.io/swerebenchv2/mgechev-revive@sha256:99086667fcee12f900994141adf66aaf745b811d6702adfc16a62ffff165f554`. | Identifies one replay, not a representative or randomly sampled case. A read-only `git show HEAD:LICENSE` in this pinned image showed the base commit's MIT license; repository copyright/notice obligations still apply. |

The replay's public test patch SHA-256 was
`004b1de637d0e6b50720929ac07c20841a6a7e3513d2e2ca897c004b19fbb9e7`;
its public gold code patch SHA-256 was
`f3579c7706d5a1b6fd47923615ebc00943cf4456eadf382857aaea90fe87038b`.
These are source-integrity references, not labels or sampling receipts.

## Controlled oracle result

The selected issue asks the Go linter to avoid a false positive for an exported
type alias. The probe used the published test patch in both runs. The container
had no network, at most 2 CPUs, 2 GiB memory and 256 processes, dropped Linux
capabilities, and `no-new-privileges`; each run had a 360-second timeout. The
image's working-tree HEAD matched the declared base commit. No provider or
study arm ran. Raw logs and patch material remained outside Git in `/private/tmp`.

| Predeclared control | Process exit | Two published fail-to-pass IDs | Published pass-to-pass IDs |
|---|---:|---|---:|
| Base commit + test patch | 1 | `TestAll` and `TestAll/unexported_return.go` failed | 492/492 passed |
| Gold code patch + test patch | 0 | Both passed | 492/492 passed |

The two failing IDs describe a parent test and its child; they are not two
independent cases. Each control produced 494 parsed test names. The base and
gold log SHA-256 digests were respectively
`7ef3b7653be367229c8c620b71e38a15911d9b2eb75ff587a1e896cedd484074`
and `bb70387480c4af8794e18a39c583eb648898773cbc6f588b1864ae7ff7ec7bae`.
This assessment ran each control once. The paper's three-run filter does not
replace an independent repeatability audit for an admitted G3 frame.

A read-only Git inspection of this image found the base commit as HEAD, no
branch or reflog entries, and no unreachable commits reported by `git fsck`.
That limits one possible answer-leak path for this case only. The public data
row itself contains the gold patch, test patch, patch-derived `interface`, and
PR description. Those fields, future Git history, test fixture expectations,
tool logs and image metadata require a defined, audited exclusion from any
model-visible task packet. The natural-language issue text was inspected for
this case and states expected behavior without the code patch; that check does
not clear other tasks or guarantee model decontamination from public training
data.

## Qualification gates

| Gate | Current finding | Disposition |
|---|---|---|
| Exact source and rights | Builder/sample/image identities pinned; full release HEAD observed. Full inventory and per-case repository rights not audited. | Open |
| Objective oracle | One Go case has a discriminating base/gold test result under controlled execution. No intentionally wrong repair, repeated local runs, ambiguity controls, or complete case audit. | Pilot evidence only |
| Leakage and contamination | Public rows expose solutions and tests; the source was built for model training. One image's Git history check passed. | Blocking for G3 admission |
| Case frame and dependence | Paper counts tasks and repositories; no project-specific eligible inventory or reviewed source-family grouping exists. Multiple tasks may share repos, tests, histories or authors. | Blocking |
| G3 outcomes and feasibility | Tests assess one repair behavior, not completion, harmful action, missed evidence or whole-task cost across six exact arms. No reviewed budget or arm implementation is bound. | Blocking |
| Single-human governance | Existing G3 verifier requires two enrolled human grader identities and ordinary-task audits; [ADR-0010](adr/0010-g3-single-human-oracle-study.md) is a planning variance only. | Blocking until prospective amendment and Joshua's signed, outcome-blind source/method disposition |

### Trust boundary and controls

The assets are the public case bytes, task projection, private future assignments,
oracle outputs and study claims. An untrusted public dataset or container can
inject commands into a model-visible issue or test path, expose answers through
patch/history fields, access the network, or produce a false pass through a
flaky/parser-dependent test. The pilot bounded container resources and disabled
network; only `/private/tmp` held public patches and replay logs. A production
qualification must pin container digests, inspect install and test commands,
keep execution isolated from host credentials and project stores, freeze the
model-visible projection before arms run, and compare an independent parser with
the task's expected IDs. A green test suite alone is not a certificate of all
task requirements or of a safe/harm-free session.

## Required next evidence for a prospective G3 source

1. Pin and inspect a full release snapshot. Produce an immutable *eligible-source*
   inventory with documented license, build, oracle, task-view and exclusion
   checks. This inventory is separate from the project sampling/label/outcome
   stores and grants no holdout assignment.
2. Freeze a task projection that omits code/test patches, patch-derived metadata,
   PR descriptions where they disclose fixes, evaluator paths and future Git
   history. Audit the projected packet and repository snapshot for leakage.
3. Reproduce base, gold, deliberately wrong and ambiguous controls under the
   pinned container/scorer across a predeclared audit set; measure flaky and
   parser failures. Keep nondecisive cases out of the eligible frame without
   repairing unknown labels.
4. Have Joshua review related tasks and define defensible assignment units and
   source-family grouping from the complete eligible inventory. Recalculate
   feasible sample size, harm bounds and inference for that frame; derive actual
   prospective selection and label-observation probabilities from the design.
5. Review exact six-arm execution and total task cost against an approved spend
   ceiling. Amend the single-human oracle schema and negative tests openly,
   preserve ordinary G3 as a separate claim, and obtain Joshua's signed,
   outcome-blind statistical/source disposition before an external timestamp or
   outcome-bearing assignment.

**Admission rule:** until all blocking gates close, use this source only for
controlled calibration or descriptive pilots. No signed G3 labels or arm
identities were issued, and the existing G3 policy seal remains unavailable.

## Primary sources

- [SWE-rebench V2 paper v2](https://arxiv.org/html/2602.23866v2): construction, stability checks, scale, diagnostic limits and intended training use.
- [Full dataset card](https://huggingface.co/datasets/nebius/SWE-rebench-V2/blob/main/README.md): schema, size and licensing.
- [Official builder](https://github.com/SWE-rebench/SWE-rebench-V2) and [20-task sample](https://huggingface.co/datasets/ibragim-bad/SWE-rebench-V2-sample): executable mechanism and replay specimen.
- [NIST Juliet C/C++ 1.3 source page](https://samate.nist.gov/SARD/test-suites/112), [guide](https://samate.nist.gov/SARD/downloads/documents/Juliet_Test_Suite_v1.2_for_C_Cpp_-_User_Guide.pdf), and [v1.3 technical note](https://samate.nist.gov/SARD/downloads/documents/Juliet_1.3_Changes_From_1.2.pdf): restricted alternative and limitations.

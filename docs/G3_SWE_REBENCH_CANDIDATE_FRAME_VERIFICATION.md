# Verification: bounded G3 source frame and issue-only task view

## Objective, authority and limits

- Requirement: create a reviewable bounded candidate case frame and a row-derived task view without promoting the public release to a G3 study source.
- Owner: Codex for construction and verification; Joshua Myers for source and statistical-method disposition.
- Starting revision: `4fbda4fa31c136e12f3dfbffa2c228985345f4b9`, clean worktree.
- Guidance selected: [Python engineering guide](PYTHON_ENGINEERING_GUIDE.md), [bounded verification guide](AGENTIC_VERIFICATION_GUIDE.md), [verification template](../templates/AGENTIC_VERIFICATION_LOOP.md), [work-note template](../templates/WORK_NOTE.md) and [threat-model template](../templates/THREAT_MODEL.md).
- Invariants: no sampling registry, custodian mapping, label store or outcome store access; no probabilities, groups, labels, splits, holdout or oracle results inferred; no provider, arm or case execution; no issue text in the metadata frame.
- Budget: one existing 429 MB public Parquet, four read-only GitHub issue/license checks, zero new Docker pulls and zero provider/study spend. Stop at issue-only source screening; a separate base-workspace and oracle audit remains.

## Decision rubric

| Gate | Evidence and result |
|---|---|
| Exact bounded frame | Pinned source byte count/hash; deterministic 453-row screen, 12-row inspection batch, 4 candidate packets; **pass as source screen** |
| Row-derived packet integrity | Packet allowlist exactly `schema_version` and `task_text`; script rebuilds/compares exact bytes and rejects mutation; **pass for row projection** |
| Issue provenance | Four exact title+newline+body matches to original GitHub issues; issues precede repair PRs; **pass for observed public text**, historical edit history not certified |
| Rights screen | Exact base-commit GitHub license blobs and file headers checked; **pass for named repository license files**, obligations and complete tree rights remain for owner audit |
| Leakage outside issue row | Base trees, future Git references, container surfaces and model pretraining not audited; **open** |
| Objective oracle and inference | No new controls, grouping, six-arm feasibility or amended verifier; **open** |

## Reproduction and independent cross-check

Rebuild from the pinned Parquet with DuckDB 1.5.5:

```sh
uvx --from duckdb==1.5.5 python tools/g3_candidate_task_views.py \
  /private/tmp/g3_swe_rebench_v2_475dd5e.parquet --write
uvx --from duckdb==1.5.5 python tools/g3_candidate_task_views.py \
  /private/tmp/g3_swe_rebench_v2_475dd5e.parquet
```

Both commands verified four packets and one frame. The source hash is checked
before DuckDB parses the file. Packet files have no source ID, repository,
license, patch, test, oracle, PR or evaluator field. The separate frame contains
no task text, prompt, patch, label, group, probability or split. The exact
candidate repository/base pairs and code/test patch bytes have no duplicate in
the pinned release; this is a structural check only.

The GitHub API returned the original issue title and body for
[carapace 251](https://github.com/rsteube/carapace/issues/251),
[policy-bot 168](https://github.com/palantir/policy-bot/issues/168),
[osv-scanner 7](https://github.com/google/osv-scanner/issues/7) and
[revive 664](https://github.com/mgechev/revive/issues/664).
An independent comparison of each API title plus newline plus body to the
Parquet `problem_statement` returned exact equality for all four. The API
also returned `LICENSE.txt` or `LICENSE` content at each recorded base
commit; file headers and Git blob IDs matched the
[frame](G3_SWE_REBENCH_CANDIDATE_FRAME.json). The original issues were created
before the corresponding merged repair PRs. All checks are read-only public
source inspection; they do not certify issue edit history or the future task
workspace.

## Negative and exposure checks

- Passing the metadata-only JSONL file in place of the Parquet returned
  `ValueError: source byte count or SHA-256 differs from pinned release`.
- Appending one space to packet 001 made read-only verification fail with
  `artifact differs from pinned source`; `--write` restored exact bytes and
  verification passed again.
- Four packet JSON objects have exactly the two allowlisted keys. An exact
  added-line scan at 10–300 characters found one 10–39-character test-line
  overlap in the revive issue's preexisting reproduction, disclosed in the
  [frame review](G3_SWE_REBENCH_CANDIDATE_FRAME.md). The other three had zero
  matches in that range. This is not a semantic leakage certificate.
- No raw logs, source patch content, prompts or outcomes were copied into the
  metadata frame. Packet text stays in the separate task-view files.

## Task-view trust boundary

| Asset or boundary | Failure mode | Control in this slice | Residual status |
|---|---|---|---|
| Pinned public Parquet to operator tool | Mutated or substituted source, duplicate or changed batch | Exact source hash/count, frozen screen counts and inspected IDs, deterministic byte verification | Publisher authenticity rests on the pinned public host, not a cryptographic publisher signature |
| Operator metadata to model task packet | Gold/test patch, PR description, evaluator or source identity crosses into task view | Two-key JSON allowlist, separate frame, exact packet hashes and mutation rejection | Future dispatcher must enforce that it sends only the packet and audited base workspace |
| Original issue text to model | Prompt injection, answer-bearing edits or links | Exact pre-PR issue match, human content screen, eight deferrals and offline/no-network future dispatch contract | Historical edits, paraphrased solution cues and model pretraining exposure remain unproved |
| Repository workspace to model | Future Git history, solution files, credentials or network tools reveal the repair or enable exfiltration | No workspace or model run created here; future run must strip Git metadata, audit base tree and isolate tools | Blocking for execution and enrollment |
| Public source and rights | Incorrect license metadata or third-party notice omitted | License file/header/blob read at each exact base commit; attribution in review record | Complete tree and redistribution obligations still require review |
| Oracle and study governance | Related tasks, flaky parser or owner-only grade mistaken for independent evidence | No labels, groups, probabilities, arms or outcomes generated | Blocking until controls and Joshua's signed disposition |

## Findings and disposition

| ID | Finding | Consequence and disposition |
|---|---|---|
| F-001 | Dataset ID suffixes identify merged PRs, while the task text came from earlier issue numbers. | Resolved for the four packets by exact original-issue comparison. Keep original issue URL in operator metadata only. |
| F-002 | `rsteube/carapace` base tree has `LICENSE.txt`, not `LICENSE`. | Resolved by exact base-tree lookup and Apache-2.0 header/blob check. |
| F-003 | Eight inspected rows have direct answer cues, mutable/external task dependencies, synthetic or ambiguous tasks. | Deferred with reasons; no packet produced. They are not silently relabeled or replaced. |
| F-004 | A clean row projection does not clear the base repository, Git history, execution image, parser, oracle or model prior exposure. | Blocking for actual G3 enrollment and model dispatch; next audit must inspect isolated base snapshots and controls. |

## Exit

- Result: bounded 12-row source inspection and four exact issue-only packets created and verified. This closes the row-projection slice only.
- Focused checks: pinned Parquet and artifact byte verification, negative source and packet mutations, independent GitHub issue comparison, exact base-license blob/header checks, duplicate structure and added-line scan passed as scoped above.
- Full repository gate: the first sandbox run reached 2,540 tests but had 31
  localhost fixture errors because socket binding was denied. The host-permitted
  rerun passed Ruff, Pyright, 2,540 source tests (4 skipped), coverage, export
  verification and wheel build. Its first installed-wheel smoke pass had one
  observer-handoff exchange error among 1,894 tests. The 11 source-tree
  observer-handoff tests and six focused installed-wheel repetitions passed.
  The complete installed-wheel smoke rerun passed all 1,894 tests. The first
  smoke failure remains an intermittent gate finding; no observer or campaign
  code was changed in this source-screening batch. The passing host-permitted
  source suite, build and smoke rerun cover the combined gate stages.
- Human review: Joshua's source/method disposition is still pending. This record grants no enrollment, signed label, assignment, preregistration or production claim.

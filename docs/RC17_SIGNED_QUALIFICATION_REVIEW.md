# rc.17 affected signed qualification review

Date: 2026-11-09 (owner local time). Owner: Joshua Myers. Operator: Codex.
Disposition: affected signed qualification passes; unpublished. This engineering
review grants neither stable-v1 approval nor live inference/publication authority.

## Candidate and source gates

`0.1.0-rc.17`, epoch 2, frozen source
`e6b1d75cc4140b7fb31c4a7a36fcdaf931c8f481`, annotated tag object
`743a28b8c2bfd7eba66a25aeb9e615064af00948`. PR #374 merged normally as
`10c9c2a841189beec641b26e0d58e7ca5e26c9db`; its 18 exact-head checks pass.
The fresh local combined gate passes: 3,969 source tests/17 skips, 2,939 wheel
tests/13 skips, 86% coverage and 912 unchanged frozen inputs. Its log SHA-256 is
`c52ae9e7c43a50587fbdb20803e7779be9caf6d8258306aee397af1f11c00fbf`.
The earlier failed combined gate remains failed; its subsequent replacement pass
is distinct. Earlier fixture failures and clock uncertainty remain recorded in
[the replay-owner work note](REPLAY_OWNER_ADMISSION_WORK_NOTE.md).

Protected [run 42685881830](https://github.com/joshuamyers22/mos-eisley/actions/runs/42685881830),
attempt 1, completed preparation and signing after the owner's GitHub approval.
The operator submitted zero approval POSTs and did not read signing-key bytes.
Protected source/wheel/container checks pass; the audit reports no known
vulnerabilities or adverse project statuses in 54 packages. Signed metadata SHA:
`3caccc95f4d4899a5aed114e504b552b90dd1c1316c445248777d7d42d0d324f`.
All four archives match the enrolled signature and their previously compared
419-file frozen runtime inventories. Runtime dependencies remain unchanged.
Canonical SBOM validation passes: 6,548 components/6,549 dependency records;
SHA `aa2c802973640983973a7e6ffd33e92d9115718679d1e9bc69530938333cc07f`.

## Complete affected evidence

| Target | Signed installation | Snapshot/SQLite offline | Published predecessor upgrades | Two-user private replay | Offline diagnostics / formula |
| --- | --- | --- | --- | --- | --- |
| Linux x86_64 | pass | pass | 13/13 | pass | pass / n/a |
| Linux arm64 | pass | pass | 13/13 | pass | pass / n/a |
| macOS arm64 | pass | pass | 13/13 | pass | pass / pass |
| macOS x86_64 | pass | pass | 13/13 | pass | pass / pass |

All 70 reports pass content and identity review, including 52 actual predecessor
journeys (rc.1, .2, .3, .5, .7, .9–.16). Each target checks rc.7's cross-epoch
rollback refusal. Installed checks cover both stores, cold resume, terminal/diff,
recovery, state preservation, tamper refusal and uninstall. Six synthetic native
diagnostic cases check bounded envelopes, refusal of replay and cleanup; their
source-review contract checks remain explicitly offline/source checks.

Legacy recorded-review replay runs as two actual non-root users in both directions:
Linux UIDs 1002/1003; macOS 610/611. Same-owner/fresh-process replay passes; private
foreign roots, readable foreign-owner roots and mixed-owner artifacts refuse.
Fixture bytes stay unchanged; accounts and fixture trees are removed. This is
the legacy replay surface, not a new complete snapshot/SQLite privacy campaign.

## Preserved failures and continuation custody

The original Intel job `129463949538` hit its 75-minute aggregate job ceiling during
rc.12; GitHub explicitly retains that timeout annotation. Its ten reports are in
artifact `13718471924`. The original run remains **cancelled**, publisher **skipped**.
Three other signed hosts retain 49 reports, with four separate replay reports.
Neither the timeout nor the earlier rc.16 startup uncertainty is relabeled passing.

[PR #380](https://github.com/joshuamyers22/mos-eisley/pull/380) introduced three
40-minute read-only shards. [Run 42735189293](https://github.com/joshuamyers22/mos-eisley/actions/runs/42735189293)
at controller `c9fe9f5fb8ca0c9b04ec2608227b7abb98a48cb0` passes all three: five
remaining Intel upgrades, offline diagnostics and generated Homebrew formula.
It uses the exact original signed artifacts and an explicit frozen e6b1d75 checkout
for runtime, qualification scripts and dependencies. Native command/startup limits
are unchanged. No original-run rerun, retag, re-sign or inference occurred.

The initial controller's hidden provenance file was excluded by the upload action.
The seven native reports were retained. A local admission refused the missing file;
that custody failure remains recorded. We do not claim to recover an original
controller receipt. Downstream custody instead verifies the exact successful run,
four fixed job IDs, three immutable artifact ZIP IDs/digests, exact bounded member
allowlists and report hashes. ZIP hashes equal GitHub's recorded digests; all
report bytes in the final review projection match their retained sources. The
correction explicitly includes the allowlisted hidden metadata and makes native
execution manual-only; subsequent PR checks verify custody without repeating native
qualification. Eleven offline admission/ZIP tests, Ruff, strict Pyright, actual
custody verification, YAML and shell syntax pass locally. All 16 executed checks
pass at 07fb528; native qualification is intentionally skipped on that correction.
Owner-directed review and normal PR #380 merge a5ab37a complete; this records
the explicit owner mandate, not independent-human attestation.

Retained local machine-receipt SHA-256 values:

- Complete release review: `29c1eea887a65c8082c4e1e3c647651aed00beedfea775cfc950f388a0cbb770`.
- 70-report content review: `2f2497c8ba224aeb95d12ef02821f3d19b7c4682ca49fedf525ee6c9e4d5472f`.
- Downstream ZIP custody: `001d7dfa5a8d10e62e477d20d756d71e9e19f6a79c4338be4711a395cc7a00d9`.

## Next boundary

Actual provider calls and new live grants remain zero. The old unapproved rc.16
memory proposal cannot authorize rc.17. Fresh requests must bind this candidate,
actual host/OS, admitted native client/authentication, memory/tools/data profile,
call/spend/retry exposure, expiry and cleanup. Qualify only the missing boundaries
identified in [R16-02](R16_02_PRIVACY_QUALIFICATION.md); retain rc.14's narrowly
scoped historical live evidence and original uncertainty. General WSL2/native
authentication, containment, enabled memory, API inspection and private-state
composition remain separate. This review does not close all v1 readiness rows,
attest independent human review, or claim prospective evaluation eligibility.

The controller correction has completed the owner-directed review and normal
merge recorded above. Any publication remains separate; the original skipped
publisher has not been enabled or bypassed. See the
[fresh request catalog](RC17_FRESH_LIVE_QUALIFICATION_REQUESTS.md) for next cases.

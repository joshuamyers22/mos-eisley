# Milestone 80 adversarial review: F2 retained authentication rejection

## Disposition

Accepted as implementation and automated verification of a narrowly retained F2
failure artifact in the real `openai-conformance` command. Rejected as operational
completion of F2, proof that OpenAI inspected or rejected a particular request body,
completion of F3 through F5, overall exit-gate completion, calibration conversion,
grading, scoring, quality, promotion, routing activation, or authority for any
provider request.

## Implemented boundary

After exact authorization succeeds and the broker admits its single-use capability,
an OpenAI authentication rejection during the input-token-count operation is recorded
in the terminal broker audit as the allowlisted pair `authentication_error` and
`token_count`. Because token counting precedes reservation, the spending ledger entry
must be absent and no `spend-reservation.json` may exist. The command compiles those
independently checked facts into a canonical status-`error` artifact and emits an
`openai.conformance.rejected` event. Cost remains null and retry, budget release,
live-result, promotion, grading, scoring, and routing authority remain false.

Retention is deliberately limited to the exact F2 tuple. The terminal audit and
compiled artifact must agree on authentication rejection at token count, absent
ledger state, and absent cost. A partial audit, launcher failure,
different provider failure, or any held, uncertain, settled, or violating ledger
state follows the existing fail-closed path and cannot mint F2 evidence. In
particular, ambiguous post-reservation failures remain artifact-free for F3.

## Adversarial findings

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| A generic local failure is labeled an OpenAI authentication rejection | Require the adapter classification and terminal audit to agree on `authentication_error` / `token_count` | The live operation still cannot prove remote body inspection |
| A rejection after reservation is presented as zero-spend F2 | Require `ledger_status=absent`, no entry, null cost, and no reservation file | The installed-wheel ceremony must independently recheck the dedicated ledger |
| A partial or forged audit mints favorable evidence | Compile against the independently persisted assignment authorization and full audit chain | Local host and artifact custody remain trusted |
| Exception text or a credential leaks into retained evidence | Persist only fixed failure enums, hashes, timing, and negative authorities | Process memory is not hardware-attested |
| F2 handling weakens ambiguous-failure conservatism | Restrict automatic failure-artifact publication to the exact pre-reservation F2 tuple | F3 still needs a separately controlled post-reservation fault |
| Automated simulation is called a live pass | Keep F2 outstanding in the gate table | A separately installed wheel and explicitly consented invalid-credential request remain required |

## Verification

The focused CLI suite exercises the actual broker redemption path with an adapter
authentication failure at token count. It parses and rehashes the retained artifact,
checks the trusted authorization and terminal audit, proves the generation method was
never called, proves no reservation or ledger entry exists, compares the full ledger
snapshot before and after, and verifies every retry and downstream authority remains
false. Separate tests prove post-reservation and pre-terminal failures do not create
this artifact. Ruff, formatting, and strict Pyright pass. The full suite passes 557
tests at 88% coverage, the package build and separately installed-wheel smoke pass,
and the locked runtime dependency audit reports no known vulnerabilities or adverse
project statuses.

## Next gate action

Build and separately install the reviewed wheel, create a fresh disposable zero-entry
failure ledger, prepare and independently sign one exact short-lived authorization,
and invoke `openai-conformance` once with explicit local data-transfer consent and a
deliberately invalid disposable credential. Reverify the installed wheel, artifact,
audit chain, absent reservation, unchanged ledger, removed container lifecycle, and
all negative authorities before marking F2 complete. No retry is authorized.

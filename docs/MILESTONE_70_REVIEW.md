# Milestone 70 adversarial review: Astra/high output-limit failure recovery

## Disposition

Accepted as a terminal, non-scoreable disposition for the tenth attempt in the
second OpenAI live-conformance campaign and as a regression fix for future
post-response validation failures. Rejected as a successful conformance result, a
retry authorization, completion of the Astra/high profile, satisfaction of failure
boundary F4, provider-authorship proof, billing reconciliation, grading, scoring,
promotion, routing activation, or authority to continue the halted campaign.

## Incident evidence

The independently authorized `gpt-6-astra` / `high` request on 2026-09-08 reached
the provider and produced a hash-bound response. Its settled receipt recorded 425
input tokens, exactly the configured 512-output-token maximum, 18,437 ms host
latency, and 29,850 micro-USD charged against the 35,600 micro-USD ceiling. The
container lifecycle reached `removed`, and the shared ledger remained unblocked
with ten settled entries, 83,439 micro-USD charged, and 216,561 micro-USD available.

The broker audit's response digest is
`3f7abf9e4288047be82f506028d820a3054d635037aa6a91d024e2dd7ecda8e1`, and its
outcome digest is
`3c9ce2a885256422db57e5cbcf90f6d77d332179dc8d93de4c1e7d6b0acadcc3`.
The strict conformance compiler rejected the response and published no success
artifact. Recovery under the corrected schema produced terminal failure artifact
`14b9645482e7689bff521c459b2bdb7a2e83ece870800afa0684cfb8f741fa4d` with
`error=invalid_response`, `failure_stage=validation`, `ledger_status=settled`, and
literal false retry, live-result, automatic-release, and promotion authority.

The exact 512-token use strongly supports output-limit truncation as the cause, but
the retained privacy boundary contains no raw provider body and the failed compiler
did not preserve a provider request ID. The disposition therefore records an
`invalid_response` rather than claiming the provider's exact terminal status or
response content.

## Implemented recovery

- `BrokeredEvaluationArtifact` schema 4 distinguishes a received-and-settled
  response that fails local validation from an exchange failure.
- Recovery binds the independent assignment, audit outcome, response hash, ledger
  entry, latency, and settled cost without storing raw response content, prompt,
  provider request ID, or invented usage.
- `openai-conformance` now writes that terminal artifact and emits a structured
  `openai.conformance.rejected` event with exit code 2.
- The offline failure compiler can backfill an orphaned received response from its
  immutable audit and ledger; supplying a live reply additionally requires its hash
  to match the audit.
- Regression tests cover incomplete-response rejection, automatic publication,
  offline recovery, reply substitution, credential non-persistence, and denial
  fields.

## Adversarial findings

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| Generic exit code 2 is treated as a preflight failure | Preserve response-received, settled-spend, latency, lifecycle, and hash evidence | The discarded raw reply prevents a stronger retrospective classification |
| A received response is relabeled as valid conformance | Fix artifact status to error with no critique, provider request ID, or usage | A later successful attempt still requires the full normal compiler and observer authentication |
| Offline recovery fabricates provider content | Derive only from an independent authorization, hash-linked audit, and exact ledger | Host, audit, and ledger custody remain trusted |
| A substituted live reply is used during failure publication | Require the supplied reply's canonical hash to equal the audited response hash | Offline recovery intentionally underclaims without possessing reply bytes |
| The failed attempt is silently retried | Keep retry false, stop campaign v2, retain unused sequences 11 and 12 | Future attempts require a new public commitment and fresh per-request consent |
| Natural truncation is counted as controlled F4 evidence | Reject F4 credit because the fault was not separately committed or injected | The five frozen failure-boundary tests remain outstanding |
| Earlier Astra/high successes are counted across the break | Reset the profile's qualifying consecutive streak to zero | Three new precommitted consecutive Astra/high successes are required |

## Gate disposition

The second campaign is halted after sequence 10; its final two commitments must not
run. Fifteen authenticated successes remain historical evidence, but the failed
Astra/high attempt breaks that profile's streak. Current gate credit is therefore 13
of 18: Luna/low, Terra/medium, Sol/medium, and Sol/high remain complete, Astra/high
requires three new consecutive successes, and Astra/max retains its first success.
No calibration conversion is authorized.

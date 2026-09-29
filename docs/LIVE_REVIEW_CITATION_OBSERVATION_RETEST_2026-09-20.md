# One bounded live citation and observation retest

## Scope and authority

- Revision: `e34c8c8706eef577d4346941a8cc84008ebc3eef`
- Manifest: `2045b5f943d6de3453e3fba9886a4fb4fadc7c71c9b2b54c36ee9c9d68396a4d`
- Profile: one attempt, two `gpt-5.6-luna` low-effort critics and one conditional
  judge; schema-2 requests; `store: false`; empty tools; zero retries
- Ceiling: 62,748 micro-USD, exactly approved before sealing and dispatch
- Non-authority: no retry, qualification, launch or routing activation

This was a fresh standalone retest of commit `e34c8c8`. It used a new private ledger,
process key, policies, manifest and approvals. No historical seal, ledger, key or
provider result was reused or changed.

## Outcome

Both critic calls reached OpenAI and returned within their approved phase. The
security critic returned a valid empty critique. The correctness critic returned JSON
with a duplicate `impact` key. The strict duplicate-key decoder rejected that answer;
a bounded non-authoritative diagnostic that retained the last duplicate value still
could not validate it as a critique. The required two-critic quorum was therefore not
met, the controller failed closed, and no judge request ran.

Because the review did not reach a retained judge result, post-result exchange
collection and observation signing were not reached. This live attempt therefore
neither confirms nor refutes the positive `source_unit` and phase-aware observation
fixes. Their deterministic offline regression, complete package gate and container
gate remain the deciding evidence.

## Accounting and cleanup

The two critic entries settled locally at 3,814 and 4,053 micro-USD, totaling 7,867
micro-USD. The unused judge reservation remains held at 20,916 micro-USD. The ledger
therefore reports 28,783 micro-USD charged/retained and one unresolved entry; this is
local policy accounting, not provider invoice reconciliation.

Both critic lifecycle records end in `removed`, and a filtered Docker inventory found
neither container. A bounded scan of private JSON, Markdown and Python artifacts found
no API-key-shaped text. No judge container was started. No retained result or signed
observation exists.

The one-attempt authority is consumed. The run grants no retry, qualification, launch
or routing authority.

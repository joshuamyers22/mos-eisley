# Milestone 72 adversarial review: v3 pre-dispatch image failure

## Disposition

Accepted as a local pre-dispatch preparation failure that did not consume campaign
v3 sequence 1. Rejected as a provider request, prompt transfer, spend event,
conformance result, retry authorization, controlled failure-boundary result, quality
evidence, or change to the 13-of-18 live gate.

## Evidence

The operator invoked the signed sequence-1 runner while it still pinned Docker image
`sha256:d14313710fa02ab72ddf2ae0b0ea1d66ad1d6c7ff1391cab930b0e8f1db19ead`.
That image was no longer present in the local daemon. The CLI had validated the
policies, read the API key into ephemeral process memory, written the trusted
assignment authorization, and constructed the broker audit before the offline
container inspected the missing image and failed closed.

The resulting audit is only `phase=prepared` with `ledger_status=absent`. It contains
an authorization file but no admission, outcome, response hash, latency, failure
classification, spend reservation, spend receipt, or container lifecycle. The v3
ledger remains unblocked with zero entries, zero charged exposure, zero unresolved
entries, and its full 600,000 micro-USD available. Because broker admission is
persisted before provider token counting, spend admission, or exchange, absence of
that record establishes that no provider request occurred through this campaign
path. The blinded prompt did not enter a container or cross the provider boundary.

The preserved preparation summary has digest
`230c5aa47c1227c3ecf50ba94a89976c2351c7db45cd18b1706a2db3b0f4e881`,
the expired signed authorization has digest
`9b6422dab89671ab77a91012916b028c37fec27594c68772dc606fcb4d8f45b3`,
and both trusted assignment copies bind authorization digest
`e8316cf871039571d07dfa52b2d20b14f331d21ea4c97487cb4e480b32af265e`.
The stub is retained privately under a name identifying the missing-image boundary;
it is not eligible for offline success or failure-artifact compilation.

The retained files contain no API-key pattern. The operator was separately directed
to unset both shell variables because their original command stopped before its
cleanup lines. Mos Eisley did not persist the credential.

## Recovery

Current source was rebuilt from the locked repository into immutable local image
`sha256:929977cba2903c990b567b1341f0d97b965ef31e670c73a4db30638204856dc7`.
Inspection verified the expected image identity and no implicit volume declaration;
an offline, read-only, no-network smoke invocation completed successfully. The
ignored v3 runner now pins that exact image ID.

The original authorization expired and will not be reused. The incomplete directory
was moved intact rather than overwritten. A fresh sequence-1 preparation may be
derived only after this public disposition, producing a new authorization identity
while retaining the same precommitted sample and route. It still requires independent
operator signing and new explicit local consent. This is not an automatic retry: no
new request is sent by recovery or preparation, and a single future provider request
remains the first admitted execution of v3 sequence 1.

## Adversarial findings

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| A generic exit code hides a provider attempt | Require the audit to lack admission and outcome and the ledger to lack every entry | Host, audit-directory, and ledger custody remain trusted |
| An absent ledger entry alone is treated as proof of no send | Corroborate it with the broker's write-before-send admission boundary and absence of any container lifecycle | Activity outside the Mos Eisley campaign path remains out of scope |
| A signed authorization is silently reused | Retain it expired in an immutable-named private directory and require fresh preparation and signature | Operator and private-key custody remain trusted |
| The failed local invocation consumes or advances sequence 1 | Keep gate credit unchanged and bind any replacement to the same committed sample and route | A later admitted non-success still halts v3 |
| Rebuilding by tag weakens image identity | Resolve the build to an immutable SHA-256 and pin that digest in the runner | Local Docker daemon and build context remain trusted |
| The API key remains in the shell after early failure | Direct explicit unsetting and verify no key pattern entered retained files | The operator's shell history and process environment remain locally trusted |
| Infrastructure repair becomes implicit send authority | Separate rebuild, public disposition, preparation, signature, and consent | The operator must still execute the exact one-request helper |

## Next gate

After this disposition merges, prepare a fresh unsigned sequence-1 authorization
against the same v3 manifest, empty ledger, committed sample, and corrected immutable
image. Review and sign it independently. A later explicit command may then authorize
exactly one provider request. Any admitted non-success halts v3; no result changes the
gate until its observation is independently signed and authenticated.

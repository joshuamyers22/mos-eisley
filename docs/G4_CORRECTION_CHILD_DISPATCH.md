# G4 contained correction-child dispatch boundary

This seventh offline G4 slice adds a separately authorized, one-use dispatch of
one correction proposal. A claimed correction cycle is **not** a dispatch grant.
The creator must sign a new exact approval binding the cycle admission, current
source revision, immutable container image, enrolled child, source-file allowlist,
brief and acceptance-criteria digests, the approved creator-test-suite claim, an
exact creator-test byte-view digest, and deadline. The proposal must be signed
by that exact child key. The grant explicitly denies provider, network, credential,
host-repository and VCS writes, and final acceptance.

## Flow and invariant

The dispatcher replays the stored correction claim, the initial candidate receipt,
its authenticated custody/control/Git chain, the current bound source inventory,
and the creator signature. The dispatch allowlist must be a subset of the approved
cycle and exclude creator tests. This slice accepts only **existing** bound source
files, not new files or deletions. It reads the assignment's exact creator-test
paths without following links, checks their complete view against the separately
signed dispatch digest, and sends that read-only view with the exact
approved-plan bytes, source, brief, criteria and cycle ceilings to an offline
proposal source. The plan bytes must match the earlier creator-approved digest. The older
creator-test-suite digest remains an approval claim; this view does not prove that
the older claim covered every test byte. A task/cycle-specific
exclusive private claim is durably written **before** invoking that source; a crash,
timeout or invalid proposal consumes the claim and requires inspection, not retry.

The returned replacement set must be signed by the enrolled child, name the exact
offer, stay within the file allowlist and reported allowance, and make at least one
byte-level change. The same deterministic validation runs in the host and in the
existing immutable-image, no-mount, no-network container. The host compares both
results, replays the current Git provenance once more, and returns a canonical
receipt retaining the complete offer, signed proposal, changed paths and digest of
the owned-file replacement set. **It never applies the replacements to the host.**

The container's signature check is not the trust anchor: the host verifies both
creator and child signatures against the enrolled policy. The offline proposal
source is a trusted injected integration point, not a production model adapter.
It must not use a provider under this grant. Its usage fields are a signed claim,
not independently measured spend; the local deadline bounds cooperative async
generation and the container run, but the callback's own infrastructure remains
trusted. The product exposes no CLI or live/provider route for this boundary.

## Remaining gates

This receipt is not a Git patch, correction-cycle completion, or acceptance.
Actual coding-child model/broker authorization and measured spending, an isolated
write/integration broker, authenticated critic quorum, a fresh custody/Git/candidate
chain, final creator and reviewer whole-suite execution, and independent
implementation review remain separate. Neither a signed proposal nor a matching
container result proves that the proposed code is correct. See the
[threat model](G4_CORRECTION_CHILD_DISPATCH_THREAT_MODEL.md),
[verification record](G4_CORRECTION_CHILD_DISPATCH_VERIFICATION.md), and
[roadmap](ROADMAP.md).

# G2 owner operated live review contract

**Decision owner: Joshua Myers. Effective 2026-09-26.** Joshua may perform the
phase authorizer, campaign observer and exact launch reviewer roles for G2. Human
independence among these three roles is not a G2 prerequisite. Earlier G2 wording
requiring separate people or independent human custody is superseded by this
decision. Requirements for independent model critics, later evaluation grading,
and G5/G6 promotion or signer custody are unaffected.

G2 still requires a prospective three-slot campaign for the exact review profile,
fresh credentialed critic/judge exchanges, owner assessment of actual runtime and
cleanup evidence after each slot, complete dedicated-ledger accounting, and a
separate signed decision for one proposed launch. The phase authority, observer and
launch reviewer use distinct enrolled identities and Ed25519 keys. Joshua may
control all three keys. Separate keys prove that the role-specific records were
signed; they do not prove independent judgment, honest host measurement or remote
provider authorship. The campaign seal and evidence hashes must be retained before
the next dependent step, and missing or failed slots cannot be silently replaced.
The initial campaign uses bounded two-hour commitment previews so the owner can
inspect and sign all three sequential slots. When a committed slot is restored,
its local dispatch window is limited to ten minutes from that restoration, even
though the sealed authorization expires later. Each phase also requires a fresh
signed scope and local exact approval.

The schema-2 `ReviewLaunchDecision` declares
`human_custody_mode: "owner_operated"` and requires explicit owner assertions that
commitment custody, the credentialed campaign and observer assessment were
reviewed. It uses the v2 launch signing domain. A schema-1 decision asserting
independent observer assessment is not accepted for a new launch. The owner must
inspect the actual evidence before signing; a synthetic fixture or successful
local verifier is not a substitute for that operating claim.
The exact signed launch scope includes the $1 owner cap and settled campaign
charge, both rechecked before credential and provider use.
The schema-2 unsigned campaign observation preview reports
`requires_owner_assessment: true`; its preview alone is never a signed observation.

`mos review-live` is the terminal composition for one Anthropic launch. It requires
the exact raw configuration and evidence hashes, sealed campaign, current guidance,
dedicated unused launch ledger and directory, pinned Docker image, operator author
identity and cap, enrolled phase and launch policies, a signed owner launch decision,
two signed phase authorizations and two local exact approvals. It prints the exact
launch scope first so the owner can sign it in a separate process. The command
never reads signer keys. At each phase, it prints the phase scope and asks for the
corresponding signed file before the local approval. The existing library rechecks
policy, evidence, guidance, runtime, signatures and spending before credential
access and provider use. Cancellation consumes the attempt and preserves uncertain
spending; it does not retry automatically.
For exact file handoff, `operator-review --phase-scope-dir` writes each campaign
phase scope outside the sealed campaign, while `review-live --launch-scope-output`
and `--phase-scope-dir` write the launch and phase scopes. Outputs are exclusive,
private files; each scope is still inert until the owner signs it.

The three-slot campaign and one exact admitted launch qualify only the committed
model, effort, prompts, token/byte limits, quorum, duration, SDK and worker image.
The current same-provider Anthropic campaign can qualify an explicitly selected
one-provider review policy. It cannot qualify the default two-provider policy or
other role profiles. G2 production completion must report that scope, the owner
operated custody mode, all attempt outcomes and ledger charges. It must not claim
independent human review, provider authorship or billing reconciliation.

For the initial owner operated run, Joshua selected a **$1 total Anthropic cap**
across the new three campaign slots and one admitted launch. Campaign preparation
requires the sum of all three worst-case allowances to fit this cap. Before the
launch and at each admission check, `review-live` adds the settled campaign charges
from its dedicated ledgers to the proposed launch's full reservation and rejects a
sum above $1. A different budget requires a new explicit owner choice and a new
exact identity, policies and commitment.

The 2026-09-27 first signed slot failed after Anthropic counted 29,282 input
tokens against a 20,000-token allowance, before generation. Its dedicated ledger
retains the full $0.21 as unresolved exposure. That campaign is not qualifying
evidence and its slot cannot be replaced inside the seal. The replacement campaign
sets an additional $0.79 cap, leaving the original $1 total unchanged. Three new
slots plus one launch can reserve at most $0.756; together with the failed $0.21
exposure the worst-case total is $0.966. The replacement review brief contains
selected G2 source excerpts with full-file hashes. Qualification of that exact
review profile does not claim a complete source audit.

The next signed slot also failed before the judge phase: Sonnet 5 returned only
reasoning after reaching its 1,300-output-token limit. Its critic call settled
at $0.043098, while the unused deferred judge allowance stays held; the full
$0.189 is counted as exposure. Both failed seals remain separate and
nonqualifying. The next proposed campaign has a $0.601 additional cap and a
focused source brief. Three new slots plus one launch reserve at most $0.558;
combined with $0.399 earlier exposure, the worst-case total is $0.957 under the
original $1 cap. No prior held allowance is released or treated as a refund.

This decision changes the G2 live review operating gate only. It grants no global
automatic activation, writing, execution authority, evaluation eligibility or
automatic simplification/routing authority.

## Executed G2 scope, 2026-09-27

The sealed focused campaign at `private/g2-owner-20260926-v7/campaign-seal`
(seal SHA-256 `685a42845cb6dbb6a4be9e6a5ed3418c1298b1fc4597cf7066938d3a374b4c53`)
has three owner-signed, accepted observations. The final campaign evidence is
`private/g2-owner-20260926-v7/slot-2-evidence.json` (SHA-256
`be2635bf6d12a07553386d16ea5e9cb4dbd826c7caa90def20a80a56033c0f4f`).
Fresh campaign review returned three qualifying attempts. The three dedicated
ledgers settled at $0.044572, $0.040870 and $0.039700, with no unresolved entries.

The first proposed launch failed before a provider exchange because the sandbox
denied Docker socket access. Its dedicated ledger retains the full $0.139500 as
unresolved exposure. The second launch completed a credentialed Sonnet critic,
but the three-minute owner launch decision expired before judge authorization.
Its ledger records $0.111286, including an unresolved $0.093 judge allowance;
the full $0.139500 launch maximum remains the conservative exposure. Both launches
are terminal and were not retried. The owner signer now uses the enrolled policy's
600-second limit, bounded by the exact scope expiry, for launch and phase records.

Joshua signed a third exact launch decision (SHA-256
`767180dc4f0be9b6226755144725e433089b4a245be0fba6f869d4fec47b03f0`).
Its Sonnet 5 critic and Opus 5.5 judge completed in
`private/g2-owner-20260926-v7/launch-3-run`; the retained result SHA-256 is
`abfa476233a471a5ead5878ca6f842ad2978853be304d18b1801c32d38b5c739`
with an accepted verdict. The independent controller inventory verified both
exchange audits and completions, a complete spending inventory, a $0.050520
settled charge and zero unresolved ledger entries. This verifies the local
credentialed path and the retained verdict, not remote provider authorship or
provider billing.

Counting the two earlier failed campaign holds ($0.399), both failed launch
maximums ($0.279), the accepted campaign charges ($0.125142), and the completed
launch charge ($0.050520) gives **$0.853662 conservative exposure** under Joshua's
$1 total cap. Unused allowances are not counted as refunds for unresolved calls.

Qualification is limited to the explicit one-provider Anthropic profile: one
Sonnet 5 critic, one Opus 5.5 judge, selected focused G2 brief, 5,000 input and
3,400 output token ceilings per role, one critic and one-provider quorum, 60-second
call limit, 600-second review limit, SDK 0.125.0, pinned Docker image
`sha256:eacd2c61b355b1f76b2a6db2fe29fee2925197a9ba03d0e941d636843c247bbd`,
owner-operated role custody and no automatic retry. The default two-provider
quorum remains unqualified. The brief contains selected source excerpts and its
source hashes predate the post-seal `review-live` relative-path fix; it is not a
current full-source audit. The campaign and launch do not establish independent
human assessment, provider authorship, billing reconciliation or global
activation.

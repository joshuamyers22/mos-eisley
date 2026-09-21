# Exact review launch admission

An owning host can now pass `ReviewLaunchAdmissionInputs` to
`BrokeredReviewConformanceProbe(..., launch=...)` to require a separate independent
decision for one exact review launch. This is a library gate. The public preview
and conformance-check commands remain inert, and no live-launch CLI or automatic
activation is introduced.

Implementation owner: Codex for Josh Myers. Acceptance uses synthetic campaign and
launch fixtures, the existing broker, signed phase/local approval flow, source and
installed-package checks, and real offline Docker workers. Provider spend is zero;
fixtures permit at most three campaign probes and one new owned launch per case.
Each launch retains the existing one-use operation and whole-review bounds.
Production independent assessment and the resulting launch decision remain pending.

## Select the campaign and proposed launch

The host supplies a `ReviewLaunchBinding` with independently selected absolute
campaign/evidence paths and exact retained seal/evidence-file hashes. Its
`ReviewLaunchAdmissionInputs` also contains the proposed `ReviewLaunchConfiguration`,
a trusted current launch-authority-policy loader and a loader for the independently
signed decision. The host constructs a fresh guided envelope, current spending
policies, reviewer and pinned workers using the existing approval flow.

Construction checks the complete campaign again, rejects incomplete or corrupt
evidence and compares exact proposed critic/judge, quorum, duration and runtime
profiles. It also verifies the owning reviewer's actual judge projection before
the first critic. The launch must use a separate ledger identity and path from
the completed campaign, preserving its dedicated accounting.

The public `launch_scope` contains the exact configuration and full critic-preview
hashes, current phase/launch authority-policy hashes, retained seal and raw evidence
hashes, SDK/image, launch ledger and artifact paths, reserved amount and deadline.
Construction does not load credentials, sign a decision, reserve funds or create
the run directory. A campaign-slot binding and launch admission cannot be selected
on the same owned flow.

## Independent decision

`ReviewLaunchAuthorityPolicy` enrolls launch reviewers independently of all campaign
and target phase authorizers and observers. Both identities and public-key hashes
must be disjoint. The host selects this current policy outside saved artifacts;
changing it invalidates the pinned scope. It fixes a UTC window, maximum reservation
and maximum decision lifetime of at most 600 seconds.

An enrolled reviewer must independently assess actual operating evidence before
deciding whether to authorize the exact exposed scope. `ReviewLaunchDecision`
requires explicit assertions for commitment custody, a credentialed campaign and
independent observer assessment. These are signed human operating claims, not facts
inferred by local verification. Different keys controlled by one operator do not
establish independent judgment. Synthetic test decisions are not production evidence.

`sign_review_launch_decision` uses a separate Ed25519 signing domain. It requires an
explicit decision, signer identity and private key; the executor never calls it.
The owning decision loader supplies the resulting `SignedReviewLaunchDecision`.
A missing, unenrolled, invalid, expired or differently scoped decision blocks before
phase-authorization loading or a local prompt. The first verified decision is pinned
for the owned attempt; replacing it with another valid signature cannot extend or
change an in-progress launch.

The signature authorizes only this exact launch under all remaining gates. It does
not replace either phase signature, either local approval, current guidance,
spending admission or worker containment. Existing conformance signatures retain
their original meaning and never become launch decisions. The gate does not grant
global activation, retry, budget release or reconstruction/resume authority.

## Recheck at use and retain evidence

Admission runs before and after phase-signature loading and local approval, before
credential loading, again after the credential loader, immediately before each SDK
operation and after its await. Each check rereads the selected decision, current
policies and exact campaign/evidence bytes, freshly verifies all three historical
slots and checks current guidance, runtime, ledger path/policy and role scope.
Deleting the current decision or replacing a policy is revocation for the next check.

SDK timeouts are capped by the controller, phase authorization, launch decision,
campaign/observer validity and observation-freshness deadlines. Revocation cannot
undo a request already sent. A change detected after an operation prevents subsequent
work and retains conservative spending; there are no automatic retries. Host policy
loaders and same-owner filesystem custody remain trusted. This gate does not provide
an external monotonic witness or detect a malicious host rolling back every trusted
input, and it does not invent independent runtime evidence.

Before the first credential access, the already-started run receives an exclusive
mode-0600 `launch-admission.json` containing the exact signed decision. Later checks
require the same bytes; missing or changed retained admission blocks subsequent
dispatch. This is a local record of the checked decision, not remote provider
authorship or independent proof of custody. `launch_decision` exposes the verified
host output for explicit inspection, including when subsequent work fails.

The existing controller owns child tasks and cancellation cleanup. Cancellation,
decline or failure consumes the flow; the host cannot rerun it or reconstruct a
prepared executable handle from its artifacts. The complete historical campaign
and its ledgers remain unchanged by the new launch.

## Acceptance cases and remaining activation

Tests cover accepted launch and exact private retention, missing decisions, missing
phase/local approval, incomplete campaigns, overlapping keys, stale/revoked policy,
revocation inside the credential loader, after count and during the judge prompt,
guidance/runtime/role changes, campaign ledger reuse, input changes, wrong scopes
and signing domains, expiry, decision replacement, deadline caps, tampered retained
admission and cancellation cleanup. Docker smoke checks run successful and cancelled
flows through actual offline workers with synthetic providers and signing keys.

Production use still requires real independently assessed live conformance evidence,
actual custody separation and a separately reviewed production launch decision.
No such evidence or signature was created during implementation, and the public
live-launch path remains unavailable.

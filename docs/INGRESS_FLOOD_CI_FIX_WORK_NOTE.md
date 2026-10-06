# Schedule read CI fixtures

- Status: fixture defaults corrected; final verification and merge are tracked in
  [PR #288](https://github.com/joshuamyers22/mos-eisley/pull/288) and the authoritative
  [PR #287 release record](https://github.com/joshuamyers22/mos-eisley/pull/287).
- Owner: Joshua Myers; explicitly authorized full checks, fixture-fix protected
  merge, final build verification and qualification closeout.

## Objective and invariants

Close the CI timing failures after the approved live-coding merge. Preserve
production authentication, attempt and event limits, receipt identity and job
acknowledgement, replay controls, fail-closed quarantine, cancellation, and all
runtime bytes. These are test fixtures; no spending logic or live qualification
scope changes. No paid model calls are needed. All 132 qualification entries stay
settled at $2.375657 of the original $10 cap with zero unresolved entries.

## Observation and correction

Merged revision `b1948c1` ran 3,587 source tests with one ingress-flood error in
[CI run 37385500719](https://github.com/joshuamyers22/mos-eisley/actions/runs/37385500719).
The shared source fixture globally selected a 100 ms read deadline intended for
hung callbacks. A controlled 150 ms first authentication reproduces quarantine:
only one of 16 permitted authentication attempts executes. The regression retains
all 16 attempts, refusal before additional signature/broker work, unchanged stored
state, and later legitimate-request acceptance.

The first fixture PR run passed its full package, container, platform and secret
checks, but its 3,587-test source job found another positive case using that same
100 ms fixture: acknowledged test-receipt admission returned no timer event.
[CI run 37479650811](https://github.com/joshuamyers22/mos-eisley/actions/runs/37479650811)
records this failure. A controlled 150 ms artifact read reproduces its `0 != 1`
assertion. The shared fixture now uses the production default two-second budget.
The source observer/validator/hung-result, cancellation and dispatch-timeout cases,
and the ingress hung-authentication case, explicitly retain 100 ms lanes. TLS,
loopback, credential and keychain fixtures inherit the production budget; their
separate request, handshake, mutation and cancellation limits remain unchanged.

## Guidance, evidence and stopping rules

Selected [Python engineering guidance](PYTHON_ENGINEERING_GUIDE.md),
[verification guidance](AGENTIC_VERIFICATION_GUIDE.md),
[verification loop](../templates/AGENTIC_VERIFICATION_LOOP.md), and
[work-note template](../templates/WORK_NOTE.md), following the repository's pinned
production-project-template guidance. The analogous TLS fixture correction is in
[PR 286's note](PR_286_CI_FIX_WORK_NOTE.md).

The initial full local source runs are retained, including sandbox refusals and
15 review-fixture timing failures. All 15 passed their exact coverage rerun without
code or deadline changes. Coverage passed at 85%, export and builds passed, and
all 2,601 installed-wheel tests passed (13 skipped). The wheel matches the already
verified merged wheel byte for byte. Report these actual aggregate results; do
not claim the failed full commands passed.

After the later shared-fixture correction, rerun the affected schedule family and
static checks. Require a clean full candidate CI run before normal protected
merge, then verify the final main tree and release artifacts. Keep logs private
outside Git. Further runs require a changed revision or an identified failure.
Stop on verified closeout or a concrete unmet gate. Reverting the fixture changes
restores old test timing without changing production behavior. Final exact-head
results belong in the linked PRs; no broader G4 or automatic routing is activated.

# Ingress flood CI fixture

- Status: focused regression verified; combined verification pending.
- Owner: Joshua Myers; authorized financial and release closeout for PR #287.
- Related: [merged-main CI](https://github.com/joshuamyers22/mos-eisley/actions/runs/37385500719).

## Objective and invariants

Close the source CI timing failure after the approved live-coding merge. Preserve
production authentication, attempt and event limits, replay controls, fail-closed
quarantine, cancellation, and all runtime bytes. This is a tests-only fixture
correction; it does not change spending logic or broaden live qualification.
No paid provider calls are needed. The qualification total stays $2.375657 of the
owner-authorized $10 cap with no unresolved spending entries.

## Observation and correction

On merged revision `b1948c1`, source CI ran 3,587 tests with one error: the
attempt-flood test reached its final legitimate request with a quarantined read
lane. The shared source fixture uses a 100 ms deadline for hung-callback tests.
Production uses two seconds. A controlled 150 ms first authentication reproduces
the fixture problem: only one of the 16 admitted authentication attempts executes
before quarantine. The flood fixture now explicitly selects the default read
lane before schedule configuration. The shared fixture and hung/cancellation
cases retain their short deadlines. The regression checks all 16 authentication
attempts, refusal before additional signature/broker work, unchanged stored state,
and acceptance of a legitimate request after the attempt window expires.

## Guidance, evidence and stopping rules

Selected [Python engineering guidance](PYTHON_ENGINEERING_GUIDE.md),
[verification guidance](AGENTIC_VERIFICATION_GUIDE.md),
[verification loop](../templates/AGENTIC_VERIFICATION_LOOP.md), and
[work-note template](../templates/WORK_NOTE.md), as required by the repository's
production-project-template guidance. The analogous TLS fixture correction is
recorded in [PR 286's note](PR_286_CI_FIX_WORK_NOTE.md).

The controlled regression failed under the old fixture and passes with the
corrected fixture. All 40 ingress, source and read-handler tests pass, including
hung-callback and cancellation cases. Required completion evidence is one combined
`make check`, required candidate CI, normal protected merge, and a verified build
of the final main revision. Keep logs private outside Git. Further verification
runs need a changed revision or an identified failure. Stop on verified closeout
or a concrete unmet gate. Reverting this fixture restores the old test timing
without changing production behavior. Final results belong in the follow-up PR
and PR #287's authoritative qualification record.

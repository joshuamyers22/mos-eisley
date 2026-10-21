# Preview audit repair and publication

- Owner: Joshua Myers
- Status: repairing the failed rc.4 release candidate
- Started: 2026-10-21 UTC
- Baseline: main `0f434eadba0a866a231e8ad2d433cdee1e2453ce`
- Candidate: `0.1.0-rc.5`; preserve the failed immutable rc.4 tag

Complete the requested signed preview qualification, reviewed publication and
Mac installation/upgrade test. The rc.4 prepare job passed source and installed
wheel suites but failed its dependency audit before signing. The locked certifi
2026.7.22 is affected by GHSA-6q48-6c7w-9gw2; the audit identifies 2026.10.19 as
fixed. The upstream advisory describes removal of emSign roots associated with
compromised intermediate keys:
https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2
Failure evidence: release run 39485949409, prepare job 118851695036. No rc.4
publication or owner-installation update occurred.

Raise the certifi minimum and refresh only its lock/export entries, then issue
a new version with the existing terminal fix. Pin CI/build uv to 0.13.4 for its
related bundled-root advisory GHSA-hq85-5cpj-mr62, and bootstrap the container's
patched pip 26.2.2 through the exact URL/hash published in Python's security notice:
https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576
Use a task-local verified uv binary for subsequent local release tooling; leave
the owner's global tools unchanged. Keep all four native platforms,
rc.1/rc.2/rc.3 signed predecessor journeys, owner-protected signing/publication,
exact asset inventory and enrolled signature verification. No trust exception,
audit suppression, tag replacement, cask publication or provider calls.

Selected guidance: `AGENTS.md`, `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`,
`templates/WORK_NOTE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`,
`templates/THREAT_MODEL.md` and `checklists/RELEASE_READINESS.md`.

Acceptance: clean audit of the updated lock; matching runtime export; focused
TLS/distribution checks; one combined candidate gate and passing exact-head CI;
new immutable mainline tag; four signed installations, twelve predecessor
journeys and two native formula gates; complete public asset verification; Mac
upgrade with preserved existing state and rollback available. Stop on changed
identity, lost state, unexpected dependency churn, failing audit/checks or missing
approval. Preserve existing worktrees and user credentials. Use disposable
fixtures for qualification. Bound to one coherent full gate per actual candidate,
focused evidence-changing reruns and zero provider spend.

Trust review: certifi supplies the TLS CA bundle to network clients and the frozen
application. Updating the bundle removes the compromised trust roots; retain TLS
verification, hash-locked dependencies and the existing enrolled application key.
Never replace roots or disable certificate validation to make tests pass. The
owner requested completion of signing, review/approval of publication and Mac
installation; technical agent review is not an independent security review.

Initial evidence: locked runtime audit passes for all 54 packages with patched
uv 0.13.4. Only certifi and the project version changed in the lock. All 39 focused
distribution tests pass. The bundle loads 120 CA roots with the affected
`emSign ECC Root CA - G3` absent and TLS hostname/certificate verification enabled;
unaffected emSign roots remain as intended in 2026.10.19. The upstream uv archive
matched both its published GitHub digest and checksum file. Lint, formatting,
typing and export checks pass. The combined gate and fresh exact-head CI remain
required before publication; retain their final evidence in the delivery PR.

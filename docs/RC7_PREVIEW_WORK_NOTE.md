# rc.7 signed qualification budget correction

- Owner: Joshua Myers
- Status: active
- Started: 2026-10-22 UTC
- Frozen runtime baseline: `d911aa5e276b11b362d9a84439f44be42775121f`
- Branch: `fix/rc7-qualification-budget`

Complete the requested installable subscription preview after rc.6 release run
[39803054182](https://github.com/joshuamyers22/mos-eisley/actions/runs/39803054182)
hit its signed Intel macOS job limit. Check `119982892366` explicitly reports:
“The job has exceeded the maximum execution time of 30m0s.” It completed native
installation and rc.1/rc.2/rc.3 upgrade checks, then was cancelled during rc.5
qualification. Formula qualification and publication were skipped. The other
three platforms passed. No failing signature or state-preservation assertion was
reported. Preserve the immutable rc.6 tag and its retained signed artifacts.

Raise the signed native job ceiling to 45 minutes and issue rc.7. Keep the
qualified runtime frozen at the rc.6 source: current main has since added
scriptable execution and session recovery, which remain a later preview scope.
Integrate this corrective branch with a merge commit so its exact head becomes
reachable from protected main, then tag that reviewed head. The existing release
verifier requires exact tag/checkout identity and main ancestry; keep that guard.
Do not roll back concurrent main changes or retarget the prior immutable tag.

Selected guidance: `AGENTS.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`,
`templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/WORK_NOTE.md`,
`templates/THREAT_MODEL.md`, `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`, and
`checklists/RELEASE_READINESS.md`. This correction changes workflow timing,
version metadata and documentation; all `src/` and `tests/` contents remain the
same as the frozen, fully checked runtime. No dependency updates.

Retained evidence: rc.6's local `make check audit` passed (3,774 source tests run,
21 skips, 85% coverage; 2,742 installed-wheel tests run, 17 skips; clean audit of
54 packages). All 17 PR #320 checks and post-merge checks passed. Enrolled rc.6
metadata and four native archives verified, including the exact tagged Mac
binary that opened and quit both correctly labeled subscription routes without
inference. Actual ChatGPT/Codex 0.163.0 and Claude 2.1.283 each completed two
exchanges across cold resume, retained their original two-call grants, and
refused a third exchange before dispatch. See
[the original work note](RC6_SUBSCRIPTION_PREVIEW_WORK_NOTE.md) for the ChatGPT
receipt-count harness correction and terminal-restoration limit.

Budget and invariants: the four live native invocations are exhausted; no extra
provider calls or replacement recovery scopes. One corrective candidate with a
45-minute native qualification ceiling, unchanged mandatory prepare checks,
four signed installations, sixteen rc.1/rc.2/rc.3/rc.5 predecessor journeys and
two macOS generated-formula gates. Require all gates and exact source/signature/
archive/installer identities before publication. Protected owner approval remains
separate from implementing-agent review. Do not skip Intel, soften assertions,
patch trust roots or suppress the dependency audit to obtain a passing release.

Acceptance: verify the correction's runtime/test/dependency content is unchanged;
run affected release/publication and metadata checks; require protected-main
integration and exact-head CI; run the tagged mandatory `make check audit` again
under the existing prepare workflow; qualify the signed candidate on all four
targets; review publication; verify public assets and state-preserving Mac
installation and put the checked bundle in Downloads. Stop publication on any
failed gate or uncertain identity/state; retain failure evidence and investigate
the concrete cause. Apple notarization/cask publication remain separate.

Local correction checks passed: 56 release-workflow, publication and distribution
tests; lint/format; exact runtime dependency export; source archive and wheel
builds. The initial focused invocation found an incomplete local environment;
after frozen dependency installation the complete focused set passed. Runtime,
tests and runtime dependency export remain byte-identical to the frozen baseline;
the lockfile changes only the project's own version. Exact-head CI and the tagged
prepare gate remain required before publication.

# Narrow-terminal preview preparation

- Owner: Joshua Myers
- Status: preparing; narrow-terminal PR #316 must merge first
- Candidate version: `0.1.0-rc.4`
- Baseline: narrow-terminal fix `2860322`, based on main `1b5267d`
- Published predecessor: immutable rc.3, source `b3f04b46fb2091e861bdf3fc5e900d933cf804b3`

Prepare the next macOS/Linux standalone preview with the narrow-terminal fix.
Preserve rc.1/rc.2 upgrade gates and add the actual published rc.3 upgrade journey
on all four native targets. Use a separate branch/worktree, disposable homes and
recorded fixtures. Do not update the owner's installation or change the enrolled
release key, protected owner environment, release inventory or immutable tags.
Homebrew cask publication remains blocked on Developer ID and notarization.

Selected guidance: `AGENTS.md`, `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`,
`templates/WORK_NOTE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`,
`templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md`, `templates/THREAT_MODEL.md`
and `checklists/RELEASE_READINESS.md`.

Acceptance: exact-head source/package/security/native checks; mainline ancestry;
signed native installations; rc.1/rc.2/rc.3 upgrades with cold resume, rollback,
interruption recovery, tamper refusal and state-preserving uninstall; exact
artifact inventory and accountable protected owner release approval. Stop on
failed checks, changed identity/state, signature mismatch or missing approval.
Bound to one combined full candidate gate, focused release regressions and exact
native/CI qualification, with zero provider calls or study execution.

Trust review: the new predecessor is allowlisted by exact immutable version and
source commit. Existing enrolled-signature, archive hash/size, bootstrap checksum
and fail-closed unknown-version checks remain mandatory. No credentials or key
bytes enter source or artifacts. Technical agent review is not independent
security approval; protected publication requires the accountable owner.

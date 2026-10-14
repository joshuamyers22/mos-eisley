# Work note: draft-first immutable publication

- Status: active
- Owner: Joshua Myers; implementation: Codex
- Started: 2026-10-14 UTC
- Review by: next release acceptance
- Related delivery: [preview #302](https://github.com/joshuamyers22/mos-eisley/pull/302)

## Objective and completion evidence

Update published preview instructions and automate draft creation, complete upload
verification and final publication. Preserve the existing immutable rc.1 tag and
assets, protected owner acceptance, signing custody, native gates and stage-only
npm controls. This task authorizes no new release, provider call, study, WSL2
claim or key custody change.

Guidance: repository `AGENTS.md`, `templates/WORK_NOTE.md`,
`templates/AGENTIC_VERIFICATION_LOOP.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`,
`docs/PYTHON_ENGINEERING_GUIDE.md`, `templates/THREAT_MODEL.md` and the existing
[installation threat model](INSTALLATION_UPDATES_THREAT_MODEL.md).

Risk is material: contents-write publication. Blocking evidence is an offline
transaction test that cannot publish before complete qualified uploads; failed
uploads, mismatched bytes/subject, extra assets and published releases must refuse.
Matching partial drafts must resume without overwrite. Normal quality gates and
exact-head CI precede accountable owner acceptance. Bound work to one combined
quality run and up to three evidence-changing correction passes; stop on unresolved
publication/identity/asset mismatch. No paid requests or public test release.

## Observations and controls

- The guide, README and memory still described unpublished packages/formula after
  rc.1 publication. Published source/CI/registry/tap evidence is in #302; the
  historical preparation records retain their original receipts with a closeout
  pointer.
- Pinned softprops v3 creates new prereleases with `draft: false` unless requested.
  The rc.1 operator prepared a draft manually. The workflow now explicitly uploads
  to a draft and finalizes only after comparing the complete uploaded inventory.
- Resumed drafts can contain a partial upload. Preflight compares retained assets
  to qualified local names/sizes/digests; it refuses substitution, unexpected assets
  and published releases before the uploader. Finalization requires the complete
  inventory and exact tag/source/preview classification before its sole PATCH.
- Repository immutability administration needs privileges absent from the workflow
  token. Existing protected owner review checks that setting; the helper uses only
  contents access and requires GitHub to confirm immutable publication. It does
  not add admin credentials or attempt to revert publication on an API error.
- Upload/verification failure leaves the draft unpublished. A publication response
  failure may occur after GitHub publishes; inspect release state instead of
  blindly retrying or deleting it. Published releases refuse replay.

## Handoff

Focused transaction checks, combined quality results and exact-head CI will be
recorded before owner acceptance. New release behavior is tested offline with
inert GitHub API fixtures; no claim of a newly published candidate is made.

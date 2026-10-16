# macOS cask preparation

- Status: active preparation; public qualification blocked by Apple signing custody
- Owner: Joshua Myers
- Started: 2026-10-15 UTC
- Baseline: main `700e81b`; immutable rc.3 remains untouched
- Requirement: plan §29.4 and the requested project-tap cask command

## Objective, authority and limits

Prepare native Apple Silicon/Intel cask packages, explicit signing/notarization
requirements, package-manager update guidance, and executable admission checks.
Publish only after real quarantined installation, upgrades, migration and removal
pass on both architectures, followed by accountable owner release review.

The user has no Developer ID. Both the local keychain and protected GitHub secret
names confirm no Apple signing configuration is provisioned. rc.3 uses ad-hoc
Mach-O signatures: `spctl` rejects it, and a disposable recursively quarantined
copy terminated with signal 9. This is blocking execution evidence, not merely a
policy assumption. No quarantine attribute was removed and Gatekeeper was not
disabled. Third-party tap signing audits are optional by default, but omitting
that audit does not make a quarantined binary runnable.

Do all independent engineering now. Development disk images and disabled casks
are review fixtures, never publication evidence. Preserve the user's installed
rc.3, original uv launcher backup, data, secrets and all other worktrees. Use no
paid provider calls and never collect/export signing keys. No Apple enrollment,
payment, new certificate, or account action is authorized by this preparation.

Selected guides: `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/WORK_NOTE.md`,
`templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`,
`docs/ADVERSARIAL_REVIEW_PLAYBOOK.md` and `checklists/RELEASE_READINESS.md`.

## Package and trust requirements

- A read-only compressed DMG contains `Mos Eisley/mos`, its complete native
  runtime, license, and an immutable `homebrew-cask` origin receipt. Homebrew
  retains the staged payload and links `mos`; no privileged installer, standalone
  runtime activation, cleanup script, `zap`, or Python/Node dependency is needed.
- Separate native ARM64/x86_64 packages; pinned immutable version URLs and SHA256.
  Preserve runtime-relative library paths and internal framework links.
- Developer ID Application signing of every Mach-O via PyInstaller, hardened
  runtime, secure timestamps and a single expected Apple Team ID. No development
  entitlement or ad-hoc fallback in production. Sign the DMG; submit with an
  owner-provisioned notarytool keychain profile, require `Accepted`, staple and
  validate the ticket, and assess Gatekeeper before emitting a production receipt.
- The requested token is `mos-eisley`; while it tracks a preview, the cask and
  documentation must explicitly identify that channel. This follows the user's
  exact project-tap command rather than silently substituting a preview token.
  It does not declare stable v1 qualified or default-tap eligibility.
- Apple Developer ID and the existing Ed25519 release root serve different
  purposes. Preserve the enrolled root and existing immutable releases. New
  runtime behavior needs a new release version before publication; never add or
  replace assets in immutable rc.3.

## Rubric, risks and stopping rules

| Gate | Required evidence |
|---|---|
| Layout | Both native DMGs mount read-only and contain runnable self-contained payloads, correct architecture and cask origin |
| Integrity | Mixed versions/source/team, missing architecture, altered DMG and incomplete notarization fail admission |
| macOS trust | Real Developer ID, hardened runtime/timestamps, accepted notarization, stapling, Gatekeeper and ordinary quarantine |
| Lifecycle | Real brew install/upgrade/uninstall on both native hosts, credential-free setup, recorded chat/cold resume, unchanged retained state |
| Migration | Explicit owner-selected formula/uv/npm/standalone migration, conflict refusal, one selected launcher, no takeover or data deletion |
| Publication | New immutable artifact inventory, owner review, protected tap PR, public command and fresh-download verification |

Threats: substituted architecture/source, forged or stale receipts, signature
changes after hashing, arbitrary internal symlinks, PATH ownership conflicts,
uninstall deleting private data, and claiming unsigned fixtures as qualified.
Checksums/JSON receipts alone do not authenticate Apple notarization. Protected
publisher review must verify native execution evidence and exact signed packages.

Bound: one combined full quality gate, focused boundary tests immediately, two
native development builds, at most three evidence-changing corrections, zero
provider spend. Stop publication on any identity/trust/state mismatch or missing
Apple custody. Do not replace missing external trust evidence with a simulation.

## Handoff

Production installation/upgrade/migration/publication remain open until the owner
can provision Developer ID Application signing and notarization. Development
layout and refusal evidence must be reported separately from those gates.

References: [Cask Cookbook](https://docs.brew.sh/Cask-Cookbook),
[Acceptable Casks](https://docs.brew.sh/Acceptable-Casks),
[Homebrew security](https://docs.brew.sh/Homebrew-Security-and-Supply-Chain),
[Apple notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution),
[PyInstaller signing](https://pyinstaller.org/en/stable/feature-notes.html#macos-binary-code-signing).

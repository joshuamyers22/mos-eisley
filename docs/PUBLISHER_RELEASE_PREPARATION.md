# Publisher security and release preparation

The application publisher controls are prepared for the owner-operated macOS/Linux distribution. Public application release and production launch require the exact candidate and advertised journeys to pass their remaining gates. Joshua Myers owns release decisions; the agent technical review does not provide independent security approval.

## Objective and verification contract

Qualify the enrolled publisher root, bootstrap trust, transactional update recovery, protected signing custody, npm OIDC staging and the official Homebrew tap. Preserve user credentials, configuration, sessions and immutable spending evidence; keep provider calls and studies disabled during qualification. Stop publication on invalid signatures, mismatched tags/commits, incomplete artifacts, failed recovery, failing CI or missing accountable disposition.

Selected guidance: `AGENTS.md`, `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md`, `templates/THREAT_MODEL.md` and `templates/WORK_NOTE.md`, using the repository's production-project-template pin. Resource ceiling: one source/control trace, one enrolled-key native journey, one coherent full quality gate, then exact-candidate CI and owner disposition. No provider spend.

## Publisher controls verified on 7 October 2026

- The existing private Ed25519 key has owned private directory/file permissions, is 32 bytes, and derives the enrolled public root in `app_release_key.py`. Key bytes were passed directly through stdin to GitHub secret encryption; no encoded copy was printed or committed.
- `application-release` requires approval by `joshuamyers22`, rejects administrator bypass and permits only tags matching `v*.*.*`. It contains `MOS_RELEASE_SIGNING_KEY_BASE64`; only its name/update metadata can be read back. Solo-owner self-approval remains enabled to avoid a deployment deadlock; this is an accountable owner gate, not an independent-review claim.
- Active repository ruleset `24668278` blocks updates and deletion of `refs/tags/v*` with no bypass actors. Tag creation still requires correct mainline ancestry, exact version checks and environment approval before secret access.
- The public [Homebrew tap](https://github.com/joshuamyers22/homebrew-mos-eisley) is initialized at `4840d0b`. Main requires PRs and resolved conversations, enforces administrators, rejects force pushes/deletion, and uses squash merge with automatic merged-branch deletion. Its disclosed solo-owner reviewer count is zero. No formula is enabled until it can reference actually published, signed immutable release assets.

## Trust and recovery review

| Boundary | Verified control | Residual condition |
|---|---|---|
| Initial bootstrap | Fixed HTTPS publisher/CDN, finite download limits and checksum verification | Checksums are not signatures. The first executable trusts GitHub HTTPS and the owner-selected publisher. Use a pinned release and inspect its source/digest. |
| Application release | Embedded Ed25519 key, exact canonical signed schema, channel/platform/epoch checks, archive sizes and SHA-256 verification | Publisher-key compromise requires stopping publication and a separately authenticated replacement bootstrap. Signed stale metadata alone does not prove freshness or current withdrawal status. |
| Extraction and activation | Reject links/traversal/special files; cap expansion; verify staged executable; owner-private root; lock active clients; durable metadata and atomic pointers | Same-user compromise is outside this boundary. Recovery validates committed state; a synthetic predecessor does not establish real historical compatibility. |
| User state | Runtime replacement/uninstall stays separate from credentials, sessions and spend records | Store migration and schema compatibility require their own reviewed tests before changing the storage epoch. |
| npm | Exact signed tag/commit and all four native hashes are verified before packaging; stage-only OIDC workflow requires the protected environment | npm owner must inspect and approve staged native packages before the launcher. Initial staging creates public `0.0.0-stage` placeholders, not available application code. |
| Homebrew | Formula generated from the admitted signed release and exact immutable URLs/checksums | Publish the formula only after assets exist; qualify manager upgrades separately and close active sessions first. |

## Candidate verification

The four native artifacts were downloaded from completed exact-main [distribution run 37657730455](https://github.com/joshuamyers22/mos-eisley/actions/runs/37657730455), binding source `47a7eb35ab89354f67e4fca5e52af0051b040f88`. The local candidate's enrolled-key signed metadata SHA-256 is `caa637a32f893a674757be24caf63aafcead7398d219609883869e4fe6b077c2`; macOS arm64 archive SHA-256 is `03107525e40b0cc3abd55d1946d0efe647381d9ef311c483011ab400e3441a86`.

The actual native bootstrap installed that signed candidate in private disposable directories with neither Python nor Node on PATH. Credential-free setup, recorded chat/cold resume, native recovery/rollback/uninstall and archive-tamper refusal passed. Session hashes were preserved across replacement/recovery. The predecessor used the same code with synthetic `0.0.0` distribution metadata and an explicitly marked private test signature. These are real executable transaction journeys, not compatibility evidence for a real prior published release. No provider calls were made.

Seven publication regression tests reject forged signatures, wrong tags/commits, incomplete platform inventories and tampered archives while admitting the complete signed set. Full preparation-branch quality results and exact-head CI will be recorded in the delivery PR.

## npm candidate staging

Authenticated account `joshuamyers22` has owner access to organization `mos-eisley`; owner-enabled 2FA is now `auth-and-writes`. All five exact-main candidate packages are staged at version `0.1.0`. Application contents remain unpublished. The launcher and macOS arm64 staged tarballs were downloaded from npm, matched their SHA-1/SHA-512 registry records, and matched all three launcher and 789 platform package members against the prepared candidate. Their actual offline local npm install, version and credential-free setup checks passed. Public application-version installation is not established by this staged round trip. Retain/review these candidates as preparation evidence; replace them if the selected final release changes runtime bytes or artifact provenance.

| Package suffix | Candidate stage ID |
|---|---|
| `mos-eisley-linux-aarch64` | `5381f08e-f465-49bd-bb1f-ea1dee3cb872` |
| `mos-eisley-linux-x86_64` | `d2b37f11-c1a6-403f-81a9-555720d174d1` |
| `mos-eisley-macos-aarch64` | `219b73be-c50e-4e7c-b8ea-d34bb3a3185a` |
| `mos-eisley-macos-x86_64` | `4576de8d-5794-4ef9-88d1-c22bc7acc866` |
| `mos-eisley` | `baebf255-c3e8-4353-b1dd-0be0d36a56e3` |

Every package uses scope `@mos-eisley`. The intended trusted-publisher binding is repository `joshuamyers22/mos-eisley`, workflow `npm-publication.yml`, environment `application-release`, permission `stage publish`. All five successful registry creation receipts confirm those exact fields and stage-only permission. The launcher binding was also read back with only `createStagedPackage` permission. A later bulk read-back attempt hit npm's expired 2FA window before completing; it is not counted as a successful five-package read-back. No direct public-publish permission was granted.

## Publisher incident and recovery procedure

Joshua Myers owns publisher-key and account incidents. Pause both release and npm staging workflows and stop environment/staged-package approvals while investigating. Remove or replace the environment signing secret through the owner-approved custody path; never print it for diagnosis. Revoke affected npm trust bindings using owner 2FA and inspect/reject suspect staged packages. Keep the Homebrew formula absent or remove the affected formula through a protected PR until an admitted replacement exists.

Preserve private GitHub/npm audit records and artifact identities, with no key values or provider payloads in repository notes. Review whether any executable assets or staged approvals were changed. Do not repair a compromised executable under an existing version/tag: retain incident evidence and issue a new immutable version.

For a compromised root, create a new dedicated key at a new private path using the enrollment tool, review the new public root, provision protected encrypted custody and build a new bootstrap. Authenticate its root through an independently owner-controlled channel; an old compromised-key signature is not proof of a safe replacement. Existing clients trust their embedded root, so do not promise seamless automatic rotation. Preserve user state while owners explicitly reinstall a verified replacement.

For key loss without compromise, restore only from the owner's approved private encrypted backup and verify that its derived public key matches the enrolled root before provisioning. Backup destination, recovery access and a restore exercise remain owner custody decisions; this task verified the local key and GitHub encrypted secret, not an independently retained backup.

## Release handoff

1. Complete preparation-branch checks and exact-head CI; review and merge the concrete workflow change through the normal protected path.
2. Obtain accountable disposition of this publisher review for the selected artifact/source identity. Protect encrypted custody and recover the local key through the owner's private backup process; do not put it in repository artifacts.
3. Select an immutable tag matching package metadata. Verify mainline ancestry, the signed source commit and all platform hashes; approve the protected signing job only for that candidate.
4. Before relying on npm OIDC, verify all five registry bindings and perform an owner-approved staged run. npm requires a first successful trusted publish within two days of configuration; reconfigure expired bindings rather than silently falling back to tokens.
5. Inspect staged packages and approve native versions before the launcher; verify actual registry installation. Admit the exact generated Homebrew formula through a tap PR after GitHub assets exist and verify actual tap installation.
6. Real predecessor compatibility, WSL2 and subscription inference remain separate qualification work. Public availability of a package is not a production-launch decision.

Publisher references: [npm trust prerequisites](https://docs.npmjs.com/cli/v11/commands/npm-trust/), [staged publishing and placeholder behavior](https://docs.npmjs.com/staged-publishing/), [trusted-publisher lifetime and provenance](https://docs.npmjs.com/trusted-publishers/), and [GitHub environment protection](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).

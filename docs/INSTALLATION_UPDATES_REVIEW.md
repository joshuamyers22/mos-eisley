# Installation and updates review packet

Repository: `joshuamyers22/mos-eisley`; branch: `feat/installation-updates`.
Date: 2026-10-06. Implementation reviewer: Codex, the implementing agent;
there is no independence claim. Accountable owner/security disposition is pending.
This uses the repository's pinned production-template adversarial review rubric.

## Recommendation

Keep the delivery PR in draft. Do not approve public installation or subscription
coding from this record. The implementation has useful local evidence, but a
publisher trust boundary, unowned npm scope, unpublished tap, absent WSL2 evidence
and incomplete manager upgrade/subscription flows remain blocking release gates.

## Architecture and boundaries

`app_release` admits inert signed metadata and bounded HTTPS downloads.
`app_install` owns extraction, runtime integrity inventory, leases, staging,
version verification, pointers, journal recovery and uninstall. `app_update`
owns discovery/cache and user/admin policy. CLI/session adapters provide explicit
confirmation and notices without paid-work restart. Distribution tools generate
native artifacts and packages; publisher signing is separate from provider auth.

`provider_auth_cli` delegates finite login/status/logout commands to owner-installed
native clients. It excludes relative/project PATH entries and explicit provider
API/token variables. This does not attest executable publisher identity, remove
native-client configuration, implement Mos subscription inference, or prove a real
account login. The source parser does not read credential values or auth files.

## Evidence and limitations

| Gate | Evidence | Disposition |
|---|---|---|
| Tamper, ownership, state, faults | 32 focused tests passed | Local evidence; final CI pending |
| Static source | Ruff check/format and strict Pyright pass | Runtime source frozen at `80b104c`; later tool checks passed |
| Standalone runtime | Committed `80b104c` macOS arm64 setup, recorded chat/resume, synthetic-version upgrade/rollback and recovery | Passed locally; other native platforms pending |
| npm | Real offline local tarball packing/install/launch | Registry ownership and publication unproven |
| Homebrew | Real isolated install/launch/formula test/uninstall of committed archive; rpath rewriting and fixture-networking defects fixed | Passed locally; public tap absent |
| Native bootstrap | Actual build/help and enrolled-key offline installation; tamper rejected; custom-root discovery/recovery/uninstall | Passed locally with host access |
| Repository/package | Complete local `make check`: source 3,616/17 skips/85% coverage; installed wheel 2,601/13 skips; export/build passed | Passed locally; final exact-head CI pending |
| New package boundaries | 32 focused installation/account cases pass from a fresh installed wheel | Added to the future package CI selection |
| Dependency audit | Locked audit, 54 packages, zero reported known vulnerabilities/adverse statuses | Passed locally |
| Native platform matrix | All four distribution jobs passed at `ed094be`; Intel bundled-libssl mismatch resolved by managed-runtime pin | Final record/test-selection head CI pending; WSL2 remains separate |
| WSL2 | No registered Windows-hosted runner | Blocked availability claim |
| Account inference | Native login command stubs tested | Subscription adapter/qualification absent |
| Publisher approval | Public root enrolled; private key outside Git | Accountable review, CI custody/protection pending |

## Findings resolved during implementation

- Preserve distribution-derived versions; a hardcoded version would reject later
  upgrades and invalidate update discovery.
- Select package smoke wheels from project metadata. A disposable future-version
  0.1.1 wheel built, installed and reported the correct version.
- Preserve frozen-library rpaths in Homebrew; rewriting dylib IDs exceeded the
  native extension header space. Exclude libexec from cleaning.
- Require managed Python 3.12.14 for native builds rather than selecting each
  runner's system interpreter. Intel CI exposed an incompatible bundled libssl;
  the corrected four-platform native CI rerun passed.
- Select the running custom standalone root for update commands rather than
  silently selecting the default root.
- Move new dispatch/proxy logic outside existing large flow functions so strict
  type checking can analyze the source without inference complexity failures.
- Bound local offline artifact reads as well as network/download extraction.
- Enforce root-owned admin policy over user policy; source projects cannot choose
  update origins or publisher keys.
- Exclude relative/project executable search paths from browser-auth selection.
- Mark WSL2 and subscription inference pending rather than implying support.

## Required accountable disposition

The owner/reviewer should bind approval to the exact commit and CI evidence,
confirm the publisher public root and private-key custody, assess bootstrap HTTPS
trust and local-runtime inventory limits, review transaction fault boundaries and
state preservation, and approve the intended support/distribution claims.

No private signing material, provider token, transcript, sampling artifact or new
paid usage belongs in this packet. Same-user compromise and publisher-key
compromise remain incident-response responsibilities. The local inventory detects
damage; it cannot defend against a same-user attacker rewriting both runtime and
inventory. Real prior-release storage compatibility remains separate from the
synthetic predecessor used for transaction testing.

# rc.16 candidate: bounded preview update discovery

Source correction and protected signing completed for [R15-01](V1_PRODUCTION_READINESS_RC15.md).
Published rc.15 remains immutable history. rc.16 is now the current immutable
published preview; [affected qualification](RC16_STARTUP_QUALIFICATION_REVIEW.md)
passes the reviewed bounded profile, retaining the non-reproduced Intel incident. [Public verification](RC16_PUBLICATION_WORK_NOTE.md) passes; stable v1 remains blocked.
Accountable review owner: Joshua Myers; next review before any new qualification
or publication. [Work note and verification](RC16_PREVIEW_DISCOVERY_WORK_NOTE.md).

## Failure and correction

GitHub's fixed ten-release API response embeds the asset inventory for each
release. The captured public response was 914,579 bytes; the previous downloader
used the 131,072-byte signed-`release.json` cap for this larger unsigned response.
It failed before choosing a preview. The source regression reproduced that exact
byte-limit refusal, while malformed JSON could also escape the controlled update
failure path.

[Discovery](../src/mos_eisley/app_release.py) now gives only that unsigned inventory
a separate **2 MiB** cap, over twice the observed response. Selection remains
limited to the same fixed ten-release page, semantic preview tags, `draft=false`
and `prerelease=true`. No arbitrary pagination, asset URLs, body text, fallback
host or credential enters discovery. Future feeds exceeding 2 MiB still refuse;
that is a finite availability limit, not permission to silently truncate or claim
an up-to-date result.

The selected `release.json` and stable metadata retain their **128 KiB** limit.
Publisher signature, channel/epoch/platform admission, trusted origins/redirects,
10-second request timeout, 60-second read deadline and explicit installation
confirmation remain unchanged. Invalid JSON encoding, numeric conversion or
excessive parser recursion becomes `ReleaseError`; the existing update checker
reports `unable_to_check` instead of a false success. No dependencies change.

## Verification and evidence scope

- Nine discovery tests use the real downloader with substituted transport:
  asset-heavy semantic selection, cap boundary and one-byte overflow, ten-record
  bound, malformed/invalid/deep JSON, draft/stable/type exclusion, stable/preview
  metadata cap, endpoint/deadline refusal and no retry after HTTP failure.
- Three added distribution cases exercise signed preview discovery through actual
  notice/confirmed fixture installation, signature tampering refusal and malformed/
  oversized `unable_to_check`. The original distribution suite passes 45 tests;
  the protected publication/workflow suite passes 18 tests.
- The exact captured public feed replays offline through the changed downloader
  and selects rc.15's genuine enrolled signed metadata. One fresh public source
  lookup also passes and verifies the same source/signature/hash. Neither is an
  installed signed-rc.16 result or a provider request.
- The frozen combined gate passed 3,960 source and 2,919 wheel tests, with 86%
  coverage and unchanged inputs. Both source PRs merged after required CI;
  protected preparation independently passed the full gate and audit.

Captured public feed SHA256:
`eb760c6de4f02df7783e7e37c3217a7e5e6b4a7644cd21b6a72961ea5bfa09bb`.
Verified public rc.15 metadata SHA256:
`a7dc636d2dc1c6078694393dd27388b5fea53cbe9bb3d2bbe61d9a18e646915b`.
Sanitized source-level lookup/replay receipt and original failed attempts remain
in ignored `.work/`; their bindings are in the work note.

## Candidate and affected qualification handoff

Project metadata and only the project record in `uv.lock` move to `0.1.0-rc.16` /
`0.1.0rc16`. Runtime dependency records/export, signing key, storage epoch and live
subscription execution paths remain unchanged. The protected workflow additionally
pins actual immutable rc.15 release `435339429`, source
`21fc2b02db5611d806626ad8c70698b3c7181577`, as an upgrade predecessor on all four
targets. Existing predecessor and rc.7 refusal gates remain required.

| Gate | Evidence and remaining limits |
|---|---|
| Source and accountable review | Exact candidate CI, normal protected merge after readiness PR #366, owner review of discovery/resource policy; completed in #366/#367; signed tag pins `14eb79d`. |
| New signed artifacts | Complete: protected build/sign; full SBOM admission; 62 reports/80 assets across all four targets, including actual rc.15 and rc.7 refusal. The original Intel failures remain preserved. |
| Installed public discovery | Complete on all four signed native targets: old rc.15 refusal, explicit rc.16 installation and public enrolled rc.15 discovery, with unchanged pointer/synthetic state and private-root cleanup. No provider calls. |
| Initial rollout from rc.15 | Actual public macOS arm64 rc.15 refusal → explicit online rc.16 installer → enrolled discovery passes, preserving synthetic state/cache. Historical session upgrade matrices remain separately bound. Real grant/uncertain-ledger and genuine future guided-restart coverage are not newly claimed. Older immutable clients need the exact verified new installer before corrected discovery can run. |
| Public notice, guided update and restart | Published rc.16 native discovery authenticates its current public release. That same-version result establishes availability, not a newer-version notice or confirmed guided upgrade/restart. Controlled signed fixtures cover offline composition; a genuine future newer-public-version lifecycle remains R16-01. |
| Live workflow reuse | This change does not modify chat/coding/auth/worker/ledger execution or authorize new calls. Keep rc.14 live evidence historically scoped; owner reviews equivalence and any independently missing profile/OS boundary. |

Preserve the dated rc.15 readiness assessment and all historical failures. This
source fix addresses the reproducer; R15-01's candidate signing, affected qualification and all four actual native
public-read discovery journeys now pass under the reviewed profile. Publication and post-publication verification now pass as recorded in the
[publication work note](RC16_PUBLICATION_WORK_NOTE.md); original failed runs remain retained. Other stable
readiness findings are unchanged.

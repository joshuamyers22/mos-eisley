# rc.15 owner acceptance and publication

Joshua Myers explicitly requested completion of rc.15 publication after the
signed qualification summary and evidence review. Acceptance covers the exact
macOS/Linux standalone preview and its disclosed affected signed/offline scope.
Installed live-workflow evidence remains recorded against rc.14; this publication
does not expand that profile, stable v1, WSL2, package-manager availability,
native billing or general reliability claims.

Selected guidance: repository working agreement, bounded verification guide,
publisher operation and threat-model/work-note templates. Bounds: one publication
approval, six-hour execution window, one public inventory/installation pass and
zero provider calls. Preserve source/tag/assets, enrolled signatures, normal
protected merges, original failures and all historical qualification receipts.

## Accepted source and evidence

Tag `v0.1.0-rc.15` targets frozen
`21fc2b02db5611d806626ad8c70698b3c7181577`; annotated object
`ac6627da26ce8ab1488197fbd525fe7f7def93e7` remains unchanged. Source PR #363 merged
normally as `83055ed6b5afe492670661ebe0cfe3b7b71f1307` after 21 checks.
[Evidence PR #364](https://github.com/joshuamyers22/mos-eisley/pull/364) merged
normally as `077e756566c65187ec4da01cbb3d93389c5ec36b` after all 14 exact-head checks.
The read-only CI watcher encountered a transport timeout; fresh API reads
confirmed successful terminal results before merge. That watcher failure remains
preserved and is not relabeled a passing invocation.

The [qualification review](RC15_QUALIFICATION_REVIEW.md) admits 58 reports and
76 prepared assets: signed installations, both-store offline matrices, 44 actual
predecessor journeys including rc.14 and rc.7 refusal, offline diagnostics and
two generated-formula journeys. All 418 packaged runtime Python files match
frozen source on each target. The real CycloneDX 1.6 SBOM has 6,485 components and
6,486 dependency records, passing canonical/schema, independent marker/reader
and malformed-inventory refusal checks. Original failures remain disclosed;
no uncertain campaign, grant or prior release was repaired or replayed.

## Protected publication

The dedicated repository immutable-release setting was enabled. Fresh guards
verified the merged evidence, exact tag/source/mainline ancestry, all 76 qualified
asset identities, enrolled signature, active immutable-tag update/deletion rules
with no bypass actors, all eleven successful prerequisite jobs and the pending
owner environment. Account `joshuamyers22` supplied exactly one owner-authorized
publication approval for run `41948231550`, attempt 1. Administrator bypass
remained disabled. No signing key was read, approval automatically retried,
workflow rerun or tag/asset retargeted.

The [protected workflow](https://github.com/joshuamyers22/mos-eisley/actions/runs/41948231550)
completed with conclusion `success`. It published immutable prerelease
[0.1.0-rc.15](https://github.com/joshuamyers22/mos-eisley/releases/tag/v0.1.0-rc.15),
release `435339429`, at `2026-11-05T14:55:24Z`. GitHub confirms `draft=false`,
`prerelease=true`, `immutable=true` and the exact frozen source.

## Public verification

GitHub CLI cryptographically verified the immutable-release attestation. Its
resolved annotated tag and full 76-asset digest map match the qualified inventory.
All 76 assets were downloaded without authentication, over HTTPS with redirect
hosts limited to GitHub and its release-asset host. Every name, size and SHA-256
matches. Public metadata verifies against the enrolled root and all four public
archives verify against its signed descriptors. The reconstructed public tree
also passes full canonical SBOM admission with 6,485 components.

The verified public `install.sh` performed a fresh online macOS arm64 install in
private disposable destinations, with neither host Python/Node nor provider
clients on the child PATH. The installed binary reports rc.15 and CPython 3.12.14;
credential-free setup passes and all 418 runtime Python files match frozen source.
Native SHA-256:
`7cf9f6715c31d020cc117233d5155f3cd0c968024283364a1b20d33520cccd2c`.
This is a fresh public consumer smoke, supplementing four-target signed/offline
qualification. It makes no new live subscription or other-platform inference claim.

## Retained closeout records

Private ordinary engineering records are under the frozen candidate's
`.work/rc15-public-verification/`. No credential, grant or raw provider content
is copied into this tracked note.

| Record | SHA-256 |
|---|---|
| Enrolled public `release.json` | `a7dc636d2dc1c6078694393dd27388b5fea53cbe9bb3d2bbe61d9a18e646915b` |
| Public `release-sbom.cdx.json` | `a86e8daa7c86b3436a27b8b58b40c1cbe8792050bd69bd2704c4e39f3ea4a3b1` |
| Owner publication acceptance | `6d6ca13382f281c9f91bc554d5f53a96c99a2a0579f5fad2c585b157c383f905` |
| Publication workflow result | `3110b7bdc712a7b4afd9b51dc466f04169987bdeb4efe40ab41a2bb43864c02b` |
| Public inventory review | `18a3d4926cadf49199efc2ce23ba157a8fca448e476848855ba7a57eefa028c0` |
| Public installation review | `081b5c97ff511d8ab3c6cc8a0e2b0f878fc0ddee97f0dfe5109452e690eb159b` |
| Immutable attestation output | `f94c6e736edc708b4a7b1d924bed4ccfb73ebd810d3b87d95a04372e5c371e76` |
| Combined publication closeout | `2fbac9522ce8d5e1b39a23e6bcc8af6027e1f8303825f183b83ef8214244d45a` |

The owner gate records accountable release acceptance; it is not an independent
security-reviewer attestation. Engineering receipts confer no evaluation
eligibility. rc.14's immutable empty SBOM and historical evidence remain unchanged;
rc.15 provides the qualified, publicly verified replacement inventory.

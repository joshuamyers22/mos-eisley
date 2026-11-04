# rc.14 owner acceptance and publication

Joshua Myers approved publication of exact frozen rc.14 after the qualification
summary and evidence review. This acceptance covers the macOS/Linux standalone
preview and its disclosed installed macOS arm64 live profile. It does not expand
stable v1, WSL2, npm/tap availability, native billing or general reliability claims.

Selected guidance: repository working agreement, bounded verification guide,
release-readiness checklist, publisher operation, threat-model and work-note
templates. Invariants: immutable source/tag/assets, enrolled signature checks,
normal protected merge, one exact publication approval, no credential/key export,
no additional provider calls and preservation of all stopped/uncertain evidence.

## Accepted source and reviewed evidence

Tag `v0.1.0-rc.14` targets `ec3211e23c4a3e2b20837114e707bc8ebcbe625a`, incorporating
`11fe46514e7962731023538fc50789c8b9d7fd45`. Its annotated tag object remains
`f6cf41ac138dd3b1020864510ca4b21440bdae53`. [Evidence PR #360](https://github.com/joshuamyers22/mos-eisley/pull/360)
merged normally at `1b3dd26bf59eb604ae7245e1223518cddbed3e7c` after all 13 exact-head
checks passed, with no administrative bypass.

The [qualification review](RC14_QUALIFICATION_REVIEW.md) preserves four-target
signed/offline success (54 reports/71 prepared assets) and both-store installed
live success on macOS arm64. The original controller's host assertion failure
remains disclosed and unchanged. The owner separately authorized the successful
SQLite-only continuation; snapshot was not repeated. Combined counts remain
28 dispatches/26 completions and two planned uncertain cancellations, with no
replay. All twelve ModelReview artifacts, approval order, fresh tests and eight
removed workers were checked. All historical roots remain preserved.

## Protected publication and public verification

Repository immutability was enabled. The exact tag, source/mainline ancestry,
merged review, signed and live evidence hashes, all 71 local asset identities,
all ten successful prerequisite jobs and the pending protected environment were
rechecked before one publication approval. Account `joshuamyers22` supplied the
owner-authorized `application-release` approval for run 41699667393, attempt 1.
No approval POST or workflow was automatically retried; no signing key was read.

The [protected workflow](https://github.com/joshuamyers22/mos-eisley/actions/runs/41699667393)
finished with conclusion `success`. It published immutable prerelease
[0.1.0-rc.14](https://github.com/joshuamyers22/mos-eisley/releases/tag/v0.1.0-rc.14),
release `434439039`, at `2026-11-04T20:50:38Z`. GitHub confirms
`draft=false`, `prerelease=true`, `immutable=true` and the exact source commit.

GitHub CLI cryptographically verified the immutable-release attestation. The
resolved annotated-tag object and complete 71-asset digest map match the qualified
inventory. All 71 assets were then downloaded without authentication from the
public release, with HTTPS redirects limited to GitHub and its release-asset
host. Every name, byte count and SHA256 matches. Public release metadata verifies
against the enrolled root and all four public archives verify against it.
Metadata SHA256: `7c74c6668ef707b4ffd12a69db12d95e633d9a710ec2b9fb8de6f06203948d3d`.

On macOS arm64, the verified public `install.sh` performed a fresh online install
into disposable private destinations, with neither host Python nor Node on its
child PATH. The installed binary reports rc.14, credential-free setup passes,
and all 418 runtime Python files match frozen source. Its native SHA256 is
`9f2651de14244fd0d46bf620b35797118c83d1a9ab3315e8d3790e2b4c931405`. No provider call or new grant was made.
This consumer smoke supplements the qualified four-target signed/offline and
both-store macOS arm64 live evidence; it does not claim live inference on the
other three targets.

## Retained closeout records

Private ordinary engineering records remain under the frozen candidate's `.work/`.
No grant, credential, raw provider payload or prompt is included here.

| Record | SHA256 |
|---|---|
| `rc14-combined-live-review.json` | `773eb9dd6eb1d29e40d209a7ae6ada8bcad130ba23724b131d891e2a068ac6a5` |
| `rc14-owner-publication-acceptance.json` | `a550eea728ace6f2f2c1e4efdd4471a847d5f478580c72e879e74b8fbd718635` |
| `rc14-publication-workflow-result.json` | `0dda72fc730f4857bf646758b54b1853c9cb3ec9288107613f5378b8f8d9b1f6` |
| `rc14-public-verification/public-inventory-review.json` | `18b0464fd1f463fd4e78d5eca273953ad463721289d6713430cd047b950dafde` |
| `rc14-public-verification/public-bootstrap-review.json` | `06ffa81d339d352fb857b0db493537fb24940b087ec735f26ff0e26f0ff38e1f` |

The owner gate is accountable release acceptance, not an independent security
reviewer attestation. Engineering receipts confer no evaluation eligibility.

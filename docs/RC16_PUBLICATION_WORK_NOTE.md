# rc.16 protected recovery publication

Status: **publication and public verification complete**. Owner: Joshua Myers; operator: Codex. Started 2026-11-06
22:08Z. Review before publication and again before any stable decision.

The owner explicitly requests protected publication of exact frozen rc.16
`14eb79d52950f340aba159815222e04e6ea864e3`, followed by public verification and v1
readiness reconciliation. This authorizes the concrete reviewed preview operation,
not stable publication, new model calls, key access, rebuilding or re-signing.
Selected guidance: AGENTS, Python/agentic/adversarial guides, publisher operation,
threat-model/work-note/verification templates, and production-template release
checklist. Existing adopted pin and comparison baseline remain separately named.

Blocking rubric: exact immutable tag/source/software; original preparation and
all separately identified qualification run/receipt bindings; full 62-report/
80-asset completeness and canonical SBOM; no paid calls, rewritten failures or
signing custody access; required CI and accountable owner gate before publication;
all unauthenticated public hashes/attestation, fresh installation/discovery and
honest scoped v1 reconciliation afterward.

Execution budget: six hours of active implementation/verification; owner approval
and CI queue/wait are accounted separately. One coherent combined gate, one
recovery publication dispatch and one owner approval POST. No automatic retry of
publication or native checks. Bound jobs/downloads/output; stop on identity, test,
cleanup or upload mismatch. If finalize errors, inspect remote release state before
any recovery. Preserve an already published immutable release and partial drafts.

The existing `application-release` environment is tag-only and holds signing
custody. It is not modified. New `application-release-publication` has no secrets,
requires owner joshuamyers22, disallows admin bypass and admits only main. Its
reviewed contents-write job cannot start before approval. The preceding admission
job is read-only and authenticates original prepared bytes plus exact successful
supplementary receipts; original cancelled/skipped jobs stay unsuccessful.

Threat review: wrong run/source, duplicate/missing/substituted report, stale or
malformed SBOM, altered signed archive/bootstrap, unreviewed ref and partial draft
must refuse. Pinned actions, immutable source/tag checks, committed digest maps,
canonical SBOM recomputation, exact upstream run identities and separate owner
approval constrain these boundaries. No signing secret, provider credential,
private history/evaluation store or raw provider content is accessed. Engineering
receipts are ordinary release metadata, not sampling/evaluation authority.

## Preparation verification

Eight offline admission tests and explicit Ruff/pyright pass. They reject wrong
run/source/attempt/status, missing/duplicate/failed/skipped required discovery,
missing original timeout, unmerged review, wrong merge graph/ancestry, moved tag,
extra/duplicate report files and changed pinned evidence. Workflow review confirms
read-only admission, main-only dispatch, owner-protected contents-write publication,
pinned actions and no signing-secret references.

The first local manifest builder accidentally used host Python 3.9 and refused
`hashlib.file_digest`; project Python 3.12 corrected that read-only invocation.
The first actual API pass correctly stopped on an obsolete merge-field assumption:
the pinned REST API omits `merge_commit_sha`. The guard now requires merged PR/head,
the exact immutable Git merge's parents/tree, and main ancestry instead. New
negative merge-graph tests pass; the original refusal is retained, not relabeled
success. [Git commit API](https://docs.github.com/en/rest/git/commits#get-a-commit)
provides the parent/tree identities. No API version downgrade or artifact rewrite.

Final workflow review made read-only pull-request metadata permission explicit in
both admission and protected publication jobs. The in-progress local combined gate
was interrupted and retained as attempt 1, not credited as passing; a final-input
combined gate repeats. No runtime, digest map, signature or candidate change.

## Accountable acceptance and protected publication

The current explicit owner request authorizes the exact macOS/Linux standalone
preview and its disclosed qualification profile. It is not stable-v1 approval,
new live subscription authority or independent human security attestation.

Recovery PR #372 merged normally as `27021b43ac8a2f181d54bf74d1335168ea313725`,
reviewed head `355922cc6173f9bf3adfc5e7124b4af7aaf80ea1`; the merge tree matches.
All executed exact-head checks pass; dispatch-only admission/publication were
skipped in the PR event and were not counted as executed then. Final combined
`make check` exits 0: 3,960 source tests (17 skips), 2,919 wheel tests (13 skips),
86% source coverage, all 897 inputs unchanged, 4,992.675 monotonic seconds.
Original interrupted, host-interpreter, API-field and CLI-metadata errors remain
retained. A mistyped merge identifier was refused before enabling auto-merge;
the actual verified head was subsequently used, without bypass.

The separate publication-only environment is ID `26526997114`, exactly main-only,
owner reviewer `joshuamyers22`, zero secrets and no administrator bypass. Original
tag-only signing environment `23705390235` is unchanged. Repository immutability
and immutable tag update/deletion rules were rechecked. Signing custody was not
read or modified.

[Protected recovery run 42324795884](https://github.com/joshuamyers22/mos-eisley/actions/runs/42324795884),
workflow `409858836`, attempt 1, ran from the reviewed main merge. Read-only
admission passed the actual run chain, fixed tag/source, complete 62-report and
80-asset digest maps, four discovery receipts, diagnostic receipt and canonical
SBOM. The admitted artifact was downloaded and independently rechecked before
publication. GitHub records one `approved` decision by `joshuamyers22`. The local
approval guard stopped at the already-advanced publish job before any POST;
operator approval POST count is **zero**, with no duplicate attempt. That guard's
original assertion remains retained, not a passing approval invocation.

All three workflow jobs succeeded. The protected job rechecked admitted bytes and
upstream identities after approval, uploaded a matching draft, verified every
uploaded name/size/SHA256, and published immutable prerelease
[0.1.0-rc.16](https://github.com/joshuamyers22/mos-eisley/releases/tag/v0.1.0-rc.16),
release **437243456**, at **2026-11-07T01:36:54Z**. Source is unchanged
`14eb79d52950f340aba159815222e04e6ea864e3`; annotated tag object stays
`cdcb8240b84de4d909d345e35a08654064763535`, storage epoch 2. No release rebuild,
new signature, tag retarget or overwrite occurred. Original run 42102119299 stays
cancelled and its publisher skipped; original Intel failures remain unsuccessful.

## Actual public verification

GitHub CLI cryptographically verified the immutable-release attestation and its
tag/digest map. All **80 assets** were then downloaded without authentication,
with HTTPS/redirect-host/size/time limits; names, sizes and SHA256 match the exact
qualified manifest. Enrolled metadata and all four signed archive descriptors
verify. Reconstructed public software passes complete canonical SBOM admission:
**6,496 components and 6,497 dependency records**. This is inventory integrity,
not native vulnerability or license clearance.

Fresh online public `install.sh` installation on macOS arm64 passes version,
credential-free setup, actual CPython 3.12.14, all 418 runtime source hashes and
forced enrolled public preview discovery of rc.16. The child PATH contains no host
Python/Node, provider clients, Git or Docker. Native executable SHA256:
`59251a50cfa57271355679ce5dc55054e2d71d6cdaee780a427654867ac595d3`.
Its synthetic sentinel/runtime pointer remain unchanged by discovery.

A separate fresh private root installs actual public rc.15, reproduces its public
discovery refusal, and explicitly upgrades online with the verified rc.16 installer.
The old failed cache and synthetic state survive installation; new native discovery
authenticates public rc.16 with no update/notification or pointer/state mutation.
Both private consumer roots are removed. This is not real grant/ledger coverage
or a genuine future newer-version notice/confirmed guided upgrade/restart.
All work made **zero provider calls**; rc.14 live evidence remains historical.

## Readiness reconciliation and retained evidence

The [current readiness assessment](V1_PRODUCTION_READINESS_RC16.md) and
[installed matrix](V1_INSTALLED_ACCEPTANCE_RC16.md) close R15-01's bounded discovery
defect for rc.16 while retaining broader public lifecycle and platform/profile,
privacy, managers/cask, operations/restore, license and owner-policy gates.
Stable v1 remains blocked. Dated rc.15/rc.14 records are byte-identical.
Fresh runtime audit reports no known vulnerabilities/adverse statuses across 54
packages; source comparison finds only `app_release.py` changed among 418 runtime
files from rc.15, with both subscription adapters/runtime export unchanged.
Fresh manager and governance observations, not inherited assumptions, bind the
remaining work list. The template comparison still pins upstream `351610f9`;
its unrelated dirty checkout is untouched.

Private ordinary engineering records reside in the publication worktree's
`.work/rc16-public-verification/`. No credentials, private signing material, grants,
raw provider content or restricted evaluation data are copied here. Engineering
receipts convey no evaluation eligibility.

| Record | SHA-256 |
|---|---|
| Owner acceptance/approval review | `37724c898b557c5c05ccab8f5fdbc39cf2c6f8f8b3b578e2aec763ab1ad3806a` |
| Protected workflow result | `23327b00a210bb2bce62437c084b3e7c74691a87accf245e8df37f01c4e98ac3` |
| Complete public inventory/SBOM review | `2feaba1bb8837174c033d07be87500cbcbfb7e6b2b0d1cb8cf4b50c2e2e29767` |
| Public clean installation/discovery | `920831b95f2fd3b1174c9725d938b14f19116ddb15b43ce452fe136434367449` |
| Actual public rc.15 rollout | `bd84045d26c76d5add1a33e582346a85001b97ea8ddd3dda1177e1aa18f07189` |
| Immutable attestation output | `54301292d60c2bb296f4ec5d4b714321e842cde17ffb880871a1314d3ff7e9d1` |
| Final combined gate | `f1e8d80e133d188c7a796380bfb405fdb3454e71b8864327ff7e230a97065842` |

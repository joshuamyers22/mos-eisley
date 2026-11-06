# rc.16 protected recovery publication

Status: preparation. Owner: Joshua Myers; operator: Codex. Started 2026-11-06
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

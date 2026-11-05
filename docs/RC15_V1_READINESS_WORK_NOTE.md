# Work note: reconcile v1 readiness against published rc.15

Status: reconciliation complete; PR quality checks remain a separate merge gate. Owner: Joshua Myers; assessment operator: Codex.
Started 2026-11-05 UTC. Review checkpoint: 2026-11-12, or before stable approval.

## Objective, authority and bounds

Reconcile the existing v1 requirements and production-template release checklist
with immutable published rc.15. Credit its SBOM fix and exact signed/offline
qualification; preserve rc.14's dated assessment and separately scoped live results.
Complete a requirement/artifact/configuration/evidence matrix with owned next work.

Selected guidance: repository AGENTS.md, README, PROJECT_BRIEF, PROJECT_MEMORY,
plan §§16–17 and 27–29, release checklist, agentic verification guide/loop and
work-note template. Adopted template pin remains 8879be48; compare the selected
upstream integration/E2E guides and checklist at immutable 351610f9 without changing
policy or the dirty template checkout.

Material documentation/readiness work: two evidence passes, one correction and
validation pass, at most three hours of assessment work excluding existing quality
checks. Zero new provider calls, grants, publication, signing-key access, study,
security-setting edits or historical-ledger changes. No sampling registry,
custodian mapping, label store or outcome store access. Engineering receipts
confer no evaluation authority or eligibility.

Rubric: exact published identity and useful SBOM must have direct evidence;
all advertised v1 gates must have evidence or explicit owned gaps; reused live
results must retain their actual source/target/profile; historical files must remain
byte-identical. Stop after reconciliation and documentation checks; outstanding
product gates require their own work and accountable owner decisions.

## Evidence passes and verification

| Pass | New evidence | Result |
|---|---|---|
| 1 | Requirement/retained release trace; exact C14→C15 runtime/lock/export/controller comparison | Useful SBOM defect closed for published C15. 417/418 runtime Python files unchanged; setup diagnostics is the only runtime change. Historical live profile remains separately scoped. |
| 2 | Fresh release/76 API identities, 5.1 MB public SBOM, npm/tap, governance, upstream template and locked vulnerability audit | Public identities/counts/hash and 54-package clean audit agree. Preview discovery fails against real inventory; bounded 914,579-byte capture and exact offline replay prove R15-01 at 131,072-byte cap. |
| Correction/validation | Current assessment, installed matrix and entry points; evidence/relative links/anchors, history and non-Markdown identity checks | 297 local links/anchors resolve, all old findings dispositioned, historical rc.14 assessment/work note byte-identical, frozen non-Markdown inputs unchanged. `git diff --check` passes. |

The first public-observation collector queried the unscoped npm name and received
404 before saving its combined record. Correcting it to the repository's official
`@mos-eisley/mos-eisley` name completed the observation. The first documentation
validator required full literal finding IDs; an abbreviated R14-02/04 reference
was expanded and a case-sensitive checker string corrected. These are collector/
validator errors, not product failures or first-attempt passes.

The first `make check` invocation failed at dependency download because the
sandbox could not resolve the registry. Its log is preserved. The network-enabled
invocation is running once through the actual combined lint/type/source/export/
build/wheel gate; no passing completion is claimed yet. Required PR CI remains a
merge gate. The exact C15 protected passing gate is separately attributed in the
assessment and is not a new result from this documentation branch.

Stop rule: reconciliation and focused documentation validation complete; missing
product gates are explicitly owned, not declared passed. No source, lock, signed
asset, native grant, historical campaign/root or template setting changed.
Accountable security/governance/stable review remains for Joshua Myers.


## Handoff and retained evidence

Current assessment: [v1 readiness](V1_PRODUCTION_READINESS_RC15.md).
Frozen evidence/remaining-case plan: [installed acceptance](V1_INSTALLED_ACCEPTANCE_RC15.md).
Next smallest engineering action: R15-01 bounded preview discovery in a new
candidate; offline original-feed regression before signing and actual public
update lifecycle. No new subscription call is needed for that slice.

Historical assessment and work note are preserved exactly from
`bca846ebcabd0d922d00d8d75840d86f466471c8` / PR #362. The new assessment supersedes
that PR's operative work list, while retaining its original dated evidence.
Current facts are indexed under `delivery.v1-readiness.rc15` in PROJECT_MEMORY.
No stable approval, accepted exception, launch schedule or budget is inferred.

Ignored ordinary engineering records are retained locally in this assessment
worktree's `.work/`; original public/private qualification records stay in their
original roots. No raw provider payload or credential is copied into these docs.

| Record | SHA256 |
|---|---|
| `remote-observation.json` | `323ddc48536a706fc403074fa814492d7b8a2ee25504580390c54b7a7e383688` |
| `governance-observation.json` | `fdb0a69789b859becadbc0d3ac4398264f93d29578cc0e47352e8814ac38b6fb` |
| `public-feed-diagnostic.json` | `0f1b8643bf3dc33a8e501afeabfd437299861ec5fa81b537bb0202d2240421c1` |
| `source-equivalence.json` | `3c300f63a3629d516a2de0ede4068eafdd4edf312eebdd3cff21d3174f73aa85` |
| `template-provenance.json` | `6c09c35dd57b06f54811ee381bbc68e88199b949ad6dc223a4cd054479acd844` |
| `dependency-audit.log` | `ffea9e3fa2e470beff3f1625056094ab9167becd162186f6dee7bdf24f12211a` |

Historical assessment SHA256:
`81d50910460c16a9a655c8fbaacedf5e0afd9a2243b5fc6f61c6224fde1b6600`.
Historical work-note SHA256:
`fdee393114c94fc7b5555d47b666e8c9f249e800d50c709b124c4f972107e4ca`.
The assessment/work-note publication is documentation review, not a release.

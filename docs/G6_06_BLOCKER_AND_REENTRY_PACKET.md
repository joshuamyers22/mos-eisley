# G6-06 blocker and re-entry packet

Status: **hold pending evidence recorded; owner/operator signatures not
authenticated**, 2026-09-28. This packet records the
current G606-01/G606-03 independence gap under the
[G6-06 plan](G6_06_BOUNDED_ROLLOUT_ASSESSMENT_PLAN.md). It does not amend the
gate contract, authenticate a reviewer or host, approve a G6-05 go, release a
cohort, authorize dispatch or assess outcomes.

## Bound evidence and present constraint

The private hold record (`private/g6_06_hold_pending_evidence_20260928T0139Z.json`, operator-local and excluded from Git)
has SHA-256
`19804cddd28165432c57820439121f1e46668b6520b1637baf8bbd79d4137954`.
It binds the [G606-03 candidate freeze](G6_06_G60603_REPRODUCTION_FREEZE.md),
the local self-recheck record (`private/g60603-self-recheck-20260928T0123Z.json`, operator-local and excluded from Git)
and the fresh replay index (`private/g60603-self-recheck-replay-index-20260928T0123Z.json`, operator-local and excluded from Git).
These private files are Git-ignored and mode `0600`; retain or transfer them
separately under approved custody.
The hold record supersedes the earlier local no-go proposal index (SHA-256
`27af59167915aea829f53ef72d871c0689c811a4bcef8769949ecf16fcdb1cf0`)
without changing the underlying source or replay evidence.

| Evidence | Exact identity and result | What it establishes |
|---|---|---|
| Candidate freeze | `candidate-freeze.json` SHA-256 `915f11454d215914e3a517f06ae18de8a09e3b9c2ffe9ddec3ae40c9f764c47e`; archive SHA-256 `1e551c259d42ca115294b5c47b5b40de70034a9fa692df694af9faf4a6d6690c` | An exact 306-source, 17-suite, 314-case local candidate; its anchor fields remain unfilled. |
| Local source rehash | Self-recheck record SHA-256 `e2ffac776a449c8c0440fbe962a2008d0e23c78555f00e4bc6fbdebde053d854`; zero archive/current-worktree mismatches across 306 bound source files | The preparer rehashed the candidate and current bound worktree. This is not a distinct reviewer's G606-01 decision. |
| Fresh clean extraction | Replay-index raw SHA-256 `2995cf49154e7d2cb4b572cf1d39f4f8dcfaa756783a70d51f084dd9211d0a7f`; canonical SHA-256 `ff450b14fd61b75e8c366f7a17651853f131e66d92a74a55dee2fd1d9ba459be` | The preparer reran the archived sources with locked dependencies on the same available host. Result: `synthetic_pass`, 314/314 cases in 17 suites, stable sources and exact source/suite metadata match. |
| Baseline and source set | Baseline canonical SHA-256 `9e04c7a549f217dbb229989c6cb912bb78642d85cf0663f5e9ed780ec3acf24a`; ordered source-set SHA-256 `07eb35d3b637be34449cdcf1e175fe6c10bdea582868967a7437711f0b937bad` | The local baseline and replay compare exactly on bound source and case metadata. They do not establish independent custody or target-build identity. |

The user reported that Joshua Myers is the only available human and that no
separate host is available. This is an operating constraint supplied by the
user, not an authenticated host inventory. The preparer cannot also issue an
independent source review or reviewer replay. No separate custodian froze a
`FrozenReproductionAnchor` before the fresh local replay. The real broker
build, host identities and reviewer credentials remain unauthenticated. A
second process or directory on the same host does not satisfy the distinct
host condition in the [G606-03 validator](../tools/g6_06_reproduction_handoff.py).
The local replay cannot be converted into an independent one by backdating
an anchor or assigning different IDs afterward.

## Gate disposition and immediate operating rule

| Gate or action | Current disposition | Consequence |
|---|---|---|
| G606-01 independent source rehash and build/host confirmation | **Open.** Local rehash matched; no distinct reviewer decision or authenticated build/host. | Do not call the source closure independently accepted. |
| G606-03 frozen anchor and independent replay | **Open.** No out-of-band pre-replay anchor, distinct replay host, authenticated reviewer or dated disposition. | Do not report `independent_reproduced` or G606-03 accepted. |
| G606-02, G606-04, G606-05 | Offline validators and candidate handoffs ready; required independent source decisions, target-host O/C faults and actual cohort assessment absent. | Their `reviewable` fixture results grant no release or assessment authority. |
| G6-01–G6-05 and G5 qualification | Independent gate decisions and a qualified policy remain open in their own packets. | No G6-05 go, R2 bounded-live release or paid dispatch. |

**Current status: hold pending evidence.** The user directed this status for
bounded-live entry under the current configuration. Continue the approved
fixed-route/full-review operation while the independent evidence is absent.
The status is recorded as a user direction; no owner/operator signature or
formal gate acceptance is asserted. This is a project status, not a
`CohortRelease` phase or signed release record. The R0–R6 synthetic chain and the
[G606-04](G6_06_G60604_OPERATING_GATE_HANDOFF.md) and
[G606-05](G6_06_G60605_ASSESSMENT_SOURCE_HANDOFF.md) handoffs stay available
for later review, without changing their authority fields.

## Re-entry sequence under the current gate contract

1. Name and enroll an actual reviewer and custodian with a documented
   separation basis, and provide a genuinely separate, independently
   controlled replay host. Record the source build and both host identities
   from authenticated observations. A different folder, process, container or
   invented identifier on this host is insufficient. For the broader G6
   release, satisfy the owner, operations and independent security roles in
   the [G6-01–G6-04 review packet](G6_01_TO_G6_04_INDEPENDENT_REVIEW_PACKET.md)
   and the G6-05 gate as well.
2. Under separate custody, verify the candidate-freeze digest and every
   archive/source/lock/protocol/command digest. A distinct reviewer inspects
   and rehashes all 306 bound sources and their imports, checks the exact
   external build/host, and records a dated G606-01 accept or reject with
   findings. If any byte or dependency differs, record a discrepancy and
   prepare a new candidate; do not repair the old index.
3. After the baseline and **before** a new replay, the custodian completes and
   freezes a valid `FrozenReproductionAnchor` outside the replay workspace.
   Bind the canonical baseline index, ordered source set, suite manifest,
   `pyproject.toml`, `uv.lock`, runner, actual broker build, negative-case
   protocol and command digests, distinct producer/reproducer and host IDs,
   freeze time and expiry. Keep the candidate's invalid anchor template (`private/g60603-candidate-20260928T0045Z/anchor-inputs.json`, operator-local and excluded from Git)
   invalid until these claims are observed and independently retained.
4. The distinct reviewer transfers the verified archive to the separate host,
   runs the exact frozen command against a fresh private output path, and
   records actual replay time and build/host identity. Compare all 306 source
   hashes, 17 suite identities and 314 case identities/counts with the frozen
   baseline. Complete `ReproductionRecord` from those observed facts and run
   the G606-03 validator. A `metadata_match` is only a structural comparison;
   separately authenticate source custody, host/build and reviewer identity,
   inspect discrepancies and record a dated accept or reject.
5. Only after G606-01 and G606-03 are independently accepted may downstream
   G606-02 handoff review and the actual G606-04 operating gate proceed under
   their own prerequisites. G6-05 qualification, G5 policy claim, exact
   target-host fault observations, approved resource ceilings and an owner/
   operator R2 release remain separate requirements. G606-05 requires a real
   closed cohort and mature follow-up; this packet cannot create one.

If the required separation or host cannot be supplied, any proposed alternative
needs an **explicit, prospectively approved change** to the G6 gate contract
with its own threat, custody and evidence review. Until such a change is
accepted, the existing gate remains open. Do not reinterpret this self-run as
independent evidence or silently waive the distinct-host predicate.

## Hold record and later formal decision

An empty field is open; do not backdate a freeze or decision.

| Required field | Current value |
|---|---|
| Project owner and operations owner identities; role separation | Open |
| Current operating status | Hold pending evidence, recorded from user direction; no signed decision claimed |
| Later formal decision or approved contract amendment reference | Open |
| Decision time, signatures and expiry | Open |
| Exact candidate, self-recheck and hold-record digests reviewed | Indexed above; owner review open |
| Independent reviewer, custodian, separate host and authenticated broker build | Unavailable/unset |
| G606-01 independent findings and G606-03 frozen-anchor/replay disposition | Open |
| R2 release, paid dispatch and assessment authority | False |

Sampling receipts are metadata only and grant no authority or holdout
assignment. This packet and its private index contain bounded paths, hashes,
counts and status only; they do not read or summarize a sampling registry,
custodian mapping, label store or outcome store, and do not infer missing
probabilities, independence groups, labels or splits.

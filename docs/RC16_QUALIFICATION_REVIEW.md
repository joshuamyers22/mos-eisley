# rc.16 affected signed qualification review

Historical disposition before fresh diagnosis: **affected qualification blocked**.
Current [diagnosis and final qualification](RC16_STARTUP_QUALIFICATION_REVIEW.md)
passes the reviewed bounded profile; this earlier blocked assessment is retained
below as the record of the original failures, not the current qualification status. Frozen software is
`14eb79d52950f340aba159815222e04e6ea864e3` (`0.1.0-rc.16`, storage epoch 2).
Published rc.15 remains the current immutable preview. rc.14 live-workflow evidence
remains historical; this task makes no fresh subscription or stable-v1 claim.

## Source, authority and protected signing

The owner requested review and merge of #366 then #367, protected signing and
affected qualification. [#366](https://github.com/joshuamyers22/mos-eisley/pull/366)
merged normally as `3344c8f5bfafe0804d5d4dd55314b853f3541a1f` after 14 checks;
[#367](https://github.com/joshuamyers22/mos-eisley/pull/367) merged normally as
`b3a239a5b1bb9ec8efd8898dfd9e5201adda0dbf` after 18. Its merged tree equals the
frozen source, retained in main history. Annotated tag object
`cdcb8240b84de4d909d345e35a08654064763535` targets that source.

The correction gives the fixed ten-release unsigned inventory a separate 2 MiB
budget; signed metadata retains its 128 KiB cap. Invalid JSON becomes controlled
check failure. Trusted origins, signatures, channel/epoch admission, dependencies,
storage and provider execution remain unchanged. See [source review](RC16_PREVIEW_DISCOVERY.md).

[Protected run 42102119299, attempt 1](https://github.com/joshuamyers22/mos-eisley/actions/runs/42102119299)
completed preparation, four native builds and enrolled signing. GitHub records
owner `joshuamyers22` approving `application-release`, with admin bypass disabled.
The operator did not read private signing custody or submit a second approval.
This is owner-directed operator review, not independent human attestation.

Protected `make check audit` passed 3,960 source tests in 4,632.513 seconds and
2,919 wheel tests in 3,099.411 seconds, with 86% source coverage; audit was clean
across 54 packages. The local frozen source gate passed the same test counts,
17 source/13 wheel skips, with all 876 inputs unchanged. All 418 packaged runtime
Python sources match the frozen candidate in each of four signed archives.

## Original timeout and bounded continuation

Linux arm64/x86_64 and macOS arm64 original signed jobs passed. Intel job
127590446087 was cancelled at 2026-11-06 00:15:02Z; GitHub explicitly reports its
75-minute execution limit. Installation, both-store acceptance and predecessors
through rc.13 passed. rc.14 was interrupted; rc.15, progress and Homebrew were
skipped. Original run status remains cancelled and its publication job skipped.
Partial Intel reports are retained separately and are not counted as a full pass.

[#368](https://github.com/joshuamyers22/mos-eisley/pull/368), merged as
`93bf1bd2c99ae8aa66f27fcbb088a31d9162c36d`, supplied separately identified
read-only signed discovery. Static review caught bootstrap text incorrectly
being decoded as JSON before dispatch; a seventh offline regression and the
corrected controller passed. Its combined gate passed 3,960 source and 2,919
wheel tests with 879 unchanged inputs.

[#369](https://github.com/joshuamyers22/mos-eisley/pull/369) prepares a separate
continuation controller, `efba0d4781f0e5e4dd3c3cfa9e2b9efe31aa9d3c`.
[Read-only run 42233939365](https://github.com/joshuamyers22/mos-eisley/actions/runs/42233939365)
repeats all 16 original Intel assertion commands, divided into four disjoint
40-minute groups. Exact command/source/version comparison passes. Admission
requires the original run/source/tag/attempt, successful preparation and three
platforms, exact cancelled Intel job and its explicit timeout annotation. Five
negative/positive admission tests and seven discovery tests pass; explicit type
and lint checks pass. All four groups must succeed before public discovery.
Neither signing nor publication is present in the continuation workflow.

The interrupted initial six-hour observation window is retained. A separate
three-hour continuation window, 14:20–17:20Z on 2026-11-06, permits one dispatch,
zero provider calls and no software/tag/asset replacement. First failures stop
dependent work and are not retried automatically.

## Required actual evidence

The full reconstruction must authenticate the enrolled metadata and exact four
archive/bootstrap/root hashes, source/version/epoch and harness identities. The
required base is 62 reports/80 assets: four signed installs, four both-store
terminal/diff/recovery matrices, 48 actual predecessor journeys across twelve
immutable releases, four six-case offline native diagnostic matrices and two
actual generated Homebrew formula installation journeys. rc.7's cross-epoch
refusal and actual latest rc.15 upgrade remain required on every platform.

Four supplementary discovery receipts must separately prove actual old rc.15
refusal, explicit exact rc.16 installation preserving sentinel/state and failed
cache, then real public preview discovery from each signed rc.16 native client.
The current public result must authenticate enrolled rc.15 metadata while
reporting installed rc.16, no update/notification and unchanged pointer/state.
These are no-provider isolated-root checks; synthetic sentinel preservation does
not requalify real grants or uncertain spending ledgers. A future public release
is still needed for a genuine newer-version notice/guided upgrade/restart case.

The SBOM must pass canonical recomputation, offline CycloneDX 1.6 schema, separate
standard marker evaluation for all four targets, pinned PyInstaller member
size/hash comparison and five rejection controls before API access. Unknown
native versions retain hashed identity; no license or vulnerability clearance is
inferred. The full report inventory is incomplete, so neither full signed reconstruction
nor publisher preflight is credited as passed.

## Retained failures and publication boundary

Earlier local fixture/type errors and interrupted gates remain in preparation
records. The initial supplementary bootstrap/JSON mismatch was fixed before
signed dispatch. A restricted local rc.15 preflight failed without retained exact
native defect; escalated diagnostic commands exited 0, then a local controller
expected the wrong policy-response field. Offline analysis corrected that
expectation; the partial preflight is not a complete passing qualification.
An early full SBOM audit correctly refused missing qualification reports; it was
not treated as success. No artifact or completeness assertion was relaxed.

The original protected publisher is skipped. Supplementary read-only evidence
cannot make that original workflow green or authorize an alternate publisher.
Publication requires a separately reviewed protected path that admits the exact
completed evidence, followed by owner authorization. This task neither creates
a draft release nor publishes rc.16. Old immutable clients need the exact new
verified installer after publication to receive the discovery correction.

Evidence is retained under the frozen candidate's
`.work/rc16-signed-qualification/` and separately identified harness worktrees.
These ordinary engineering records confer no prospective evaluation eligibility.
All historical release, campaign, grant, ledger and source roots remain intact.

## RC16-Q02: fresh staged native version timeout

Recovery group 0, job 127946693481, failed before writing a signed-install
receipt. `smoke_app_distribution.py:614` invokes `install` in its synthetic
interruption fixture; `app_install.verify_binary` runs the staged `mos --version`
with a 30-second deadline. That deadline expired before activation. The actual
publisher bootstrap portion had completed, and the original Intel installation
and both-store reports passed, but this fresh failure remains blocking. No
CPU/load/loader trace or exact native partial output was retained; root cause is
undetermined. No deadline change, automatic rerun or candidate replacement follows.

The dependent installed/progress/formula checks were skipped. Public discovery
must remain skipped because every recovery group is required. The three remaining
predecessor groups may contribute separately scoped successful reports; they
cannot erase this failure or complete affected qualification. Owner: Joshua Myers;
next action: bounded startup/loader diagnostics for this exact staged executable,
then review any correction/profile change before a new qualification attempt.

Retained failed job log SHA-256:
`852176144289f91eb722b01f1c80cc7140b243ccde3878a5beb5b762fa35e1b7`.

## Audited partial disposition and evidence bindings

All three predecessor recovery groups passed; all 48 actual predecessor journeys
are authenticated, including rc.15 and rc.7 refusal on every target. Reconstruction
admits exactly **60 successful reports as partial evidence**: 46 from three full
original targets, two original Intel install/installed reports and twelve fresh
Intel predecessor reports. Original Intel duplicate predecessor reports remain
separate. The two missing base reports are Intel progress and Homebrew. The fresh
Intel install failure blocks qualification even though earlier install receipts
exist. No four-target discovery run executed; its dependency gate skipped it.

Software-only SBOM review passes canonical recomputation, the official offline
CycloneDX schema, independent 42-package macOS/44-package Linux marker selections,
and pinned-reader size/hash agreement for 164/164/163/166 bootstrap members
(Linux arm64/x86_64, macOS arm64/x86_64). Its 6,496 components and 6,497 dependency
records describe the actual prepared software. All five mutated BOMs are refused
offline by the completeness validator; no API is invoked. All 18 software files
remain unchanged. This software-only result is not complete publication admission
or a successful publisher preflight.

| Evidence | SHA-256 |
|---|---|
| Enrolled release.json | `1882d3db109ebc3b6f0d5c84de8dec0eecde96a47da5f72ad444d133b30ea3bc` |
| Signed software SBOM | `fe6a63592576d0ed2a6786c725ca5bd0d22bf242df3ddee982d30b1016c9a65f` |
| Partial 60-report reconstruction | `c18f6fa98fa17b19402b7ec52308645237aed44c4f3f1e305d5b011a4885554c` |
| Software-only SBOM audit | `e39469612903a5fb1ef39c2a0922e0604e99f3e53dc552dbce604f94c704f780` |
| Packaged runtime source review | `dec712ae6aae8959c1448475bc538e625d7a0f14be9bad04c719caeded5599cb` |
| Prepared software hashes | `595673be4420f5e9cf76b5b1324b684ddf71b42e86ea3ff41319a6a7f358b853` |
| Original protected preparation log | `33311886cb52d40dfc79d860386d903a8dc8b5f6d983e079f95fbc5e9aed1fa2` |
| Fresh Intel failure record | `5b3be6131f38b44acd48dc73257cc1209c95c9c83ac0dcd88468e08c7cf2d9bf` |
| Exact original Intel command comparison | `e8ab685165c75e2370580128088293ffda157d4a79b76ca1a75d1c1203f18b17` |

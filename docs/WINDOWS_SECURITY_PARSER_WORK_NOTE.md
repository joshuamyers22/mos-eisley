# Pure Windows owner/DACL parser work note

Status: implementation and publication verification complete; accountable review
pending. Owner: Josh Myers. Date: 2026-10-04.
Baseline: `c42eec8`; branch: `feat/windows-security-parser`. The uncommitted
Windows root-security definition is carried forward in this batch.

## Objective, guidance and limits

Implement only the pure decoder in
[the Windows root-security contract](WINDOWS_ROOT_SECURITY_CONTRACT.md), WS-01/02.
The immutable result is untrusted metadata, not a lease or admission. No native
queries, token cleanup changes, selectors, enrollment or writers are in scope.

Guidance: [Python engineering](PYTHON_ENGINEERING_GUIDE.md),
[verification](AGENTIC_VERIFICATION_GUIDE.md),
[adversarial review](ADVERSARIAL_REVIEW_PLAYBOOK.md), and the repository
work-note, verification-loop, threat-model and adversarial-review templates.
This is a material security parser change; accountable approval remains separate.

| Blocking dimension | Acceptance evidence |
|---|---|
| P-01 Frozen profile | Independent literal synthetic goldens; complete owner and ACE SID equality; exact control/revision/mask/type/flags |
| P-02 Bounded malformed input | All prefix truncations, overlapping/misaligned/out-of-range offsets, length/count limits, reserved and unsupported forms refuse with stable errors |
| P-03 Inert metadata | Clean-process import/decode traps, immutable private reprs, no native dependency, selectors still gated |
| P-04 Delivery | Same portable cases from source and dependency-free installed wheel; lint, typing, related boundary regressions |

Ceiling: three corrective passes and 90 minutes active work. Stop once rubric and
focused delivery checks pass; full combined `make check` is required before
publication. Escalate policy changes instead of broadening the frozen profile.

## Threat and failure model

Caller bytes are hostile. Bound input before reading, validate each extent before
unpacking/slicing, and forbid overlapping owner/ACL components. No pointer or
native validator sees untrusted bytes. Exact types exclude mutable/overridden
inputs. Full binary SID comparisons prevent RID/name confusion. Fixed one-ACE
policy prevents hidden foreign/inherited/generic grants. Errors/reprs expose no
SID or descriptor bytes. Allocation slack is ignored only after declared ACL
extent and sole ACE are validated. Forged metadata proves neither live protection
nor custody. Malformed and positive fixtures are synthetic; they are not native
Windows qualification evidence.

## Evidence and handoff

The decoder validates bounded self-relative bytes before every unpack/slice,
accepts only the two frozen controls and one explicit owner full-control ACE, and
returns immutable normalized metadata. The sole ACE's declared extent excludes
application data; declared ACL padding may be ignored only within its validated
allocation. Component packing order/padding do not affect equality; the permitted
auto-inherited control bit does. No native modules are imported or live inspector
exported. The contract explicitly records DWORD-aligned ACL allocation size.

| Check | Result |
|---|---|
| Source parser and related identity/wire/public-storage/principal/file boundary selection | 110 tests pass, no skips, using `PYTHONPATH=src:tests` and Python 3.12 |
| Parser cases | 23 tests pass, including literal goldens, all packed-golden single-byte mutations, every prefix truncation, 0/15-subauthority SIDs, 64 KiB cap, overlap, padding and import/I/O traps |
| Focused coverage | Parser statement/branch coverage 100%; all 61 statements and 24 branches covered |
| Build | Hatchling wheel and sdist build pass |
| Installed wheel | `tools/smoke_platform_files.py` passes in a fresh dependency-free venv with installed-path checks; 164 platform tests, eight native-Windows skips on macOS, plus separate legacy-fixture tests. All 23 parser cases pass without skips |
| Static checks | Repository-wide Ruff lint/format and strict Pyright pass; `git diff --check` and local documentation link targets pass |

The first broad wheel attempt encountered sandbox refusal when an existing POSIX
fixture bound its local socket. The same runner passed outside the sandbox;
no fixture suppression or skip was added. Portable parser tests are added to the
Windows source job, native-required wheel selection and ordinary package smoke.
Actual Windows CI has not run for this batch; synthetic descriptors are not
native DACL qualification.

Adversarial source review traced each unpack/slice to an earlier bounds check,
checked that full declared ACL extents participate in overlap refusal, and
confirmed no count-driven traversal, mutable result, private error output or
live authority. The mutation campaign adds executable evidence beyond this
agent's source review; accountable security review remains pending.

P-01–P-04 pass for this portable slice. Stop: implementation/delivery threshold
met. The subsequent publication gate, `make check`, **passes** with the locked
Python 3.12 environment: Ruff lint/format, strict Pyright, 2,865 source tests in
2,478.140 seconds (12 skips), 86% repository coverage, frozen dependency-export
verification, wheel/sdist build and 2,119 installed-wheel tests in 1,682.593 seconds
(eight skips). Skips are not native qualification evidence. Locked environment
setup required network access after sandbox DNS refusal; the combined gate ran
outside the sandbox for existing local-socket integration fixtures. No runtime
changes followed the passing gate; only this verification record was updated.

User-authorized commit and push follow the passing gate; no PR was requested.
Native inspector follows prerequisite identity review and resolution of token-close
uncertainty; owned leases and child reads remain later batches.

## PR preparation against current main

The later publication request authorizes a PR against `main`. Current main
`5a6be4e` was integrated without conflicts; its changes are limited to the three
`CONVERSATION_DIFF_*` review/acceptance documents. Source, tests, tools, CI, build
and dependency inputs are unchanged from the full-gate parser commit `8a38199`.
The passing combined gate therefore remains the runtime evidence; no duplicate
full run was needed for this documentation-only integration. Local link targets
and `git diff --check` pass. GitHub CI must verify the published head.

This branch is stacked on already-open #266, #268, #270, #272, #273 and #275.
Merge/review prerequisites in that order before the parser PR so its remaining
diff is the bounded Windows parser batch. The stack does not grant native
identity/storage admission or resolve token-close uncertainty.

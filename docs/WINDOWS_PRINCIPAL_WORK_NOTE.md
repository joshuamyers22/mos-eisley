# Native Windows principal-query slice

Status: local implementation and combined gate complete; native qualification and
selector admission pending. Owner: Josh Myers. Started: 2026-10-03. Base: 9285c56, clean
`feat/windows-principal-query` worktree stacked on identity PR #264.

Objective: implement only the native process TokenUser observation in
[plan §27.2](mos-eisley-plan.md#272-version-011--full-native-windows-support) and
[the identity contract](PLATFORM_IDENTITY_CONTRACTS.md). The candidate target is
64-bit AMD64 CPython 3.12+ on Windows 10/Server 2019 or later (build 17763+).
Actual architecture/version coverage must be recorded by native CI. Public
`identity.current_principal` remains closed on Windows until native evidence and
accountable boundary review admit the selector. The adapter's direct entry point
is available for qualification; it grants no storage or authorization policy.

Selected guidance: [Python guide](PYTHON_ENGINEERING_GUIDE.md),
[verification guide](AGENTIC_VERIFICATION_GUIDE.md),
[verification loop](../templates/AGENTIC_VERIFICATION_LOOP.md),
[work-note template](../templates/WORK_NOTE.md),
[threat-model template](../templates/THREAT_MODEL.md),
[existing threat model](PLATFORM_IDENTITY_THREAT_MODEL.md), and
[ADR-0014](adr/0014-platform-identity-contracts.md).

## Blocking rubric and limits

- P-01: inert imports; only supported candidate native hosts may load system DLLs;
  unknown/unqualified hosts refuse before loading.
- P-02: fresh process TokenUser SID, independent native oracle and environment
  spoofing test; SID equality is metadata, never privilege/access proof.
- P-03: thread-token presence refuses before process-token access; only
  ERROR_NO_TOKEN permits proceeding. Recheck before returning, close every owned
  token, preserve failure causes, never change impersonation or privileges.
- P-04: sizing plus at most two bounded queries, at most 64 KiB per owned buffer;
  returned structure/header/body pointers proven in bounds before validation,
  native SID validation/length and copied full SID bytes.
- P-05: fault injection for API errors, malformed sizes/pointers/SIDs, retry limits
  and cleanup; actual native thread impersonation and handle-count evidence.
- P-06: source and isolated installed-wheel tests; combined `make check`; unchanged
  existing consumers, serializers and public unsupported Windows selector.

Risk: material native identity/FFI boundary. Ceiling: three material correction
passes, four hours active work excluding long established full gates. Stop after
focused/static/artifact checks and one frozen combined local gate. Native evidence
unavailable on this macOS host is pending, never passed. Accountable review is
required before selector admission, qualification or consumer/schema adoption.
No file-identity query, NTFS detection, migration, DACL, path opening, storage
writes, execution, credential changes or broader Windows/CLI qualification.

## Evidence and handoff

A resource review found repeated DLL binding construction on each query. Lazy,
lock-protected process-lifetime bindings now prevent repeated loads; thread tokens,
process tokens, buffers and identifiers are never cached. A regression test observes
one binding construction, two token acquisitions and changed SID results. The first
combined gate was terminated during the source suite to incorporate this correction;
it is not recorded as passed. The new combined gate passed on the corrected frozen code.

Focused macOS source platform tests: 55 collected, 51 passed, four actual native
Windows cases skipped explicitly. A fresh wheel-only environment gives the same
55/51/four result and verifies all three platform modules reside in that environment.
Lint, formatting, strict typing, runtime export and source/wheel builds passed.
`MOS_REQUIRE_TMUX=1 make check` exited 0: 2,739 source tests in 2,233.326 seconds
(eight skips: four existing, four native Windows), 86% coverage, and 1,987
installed-wheel tests in 1,460.089 seconds (four native Windows skips). No native case is
claimed as executed on this host. The native-required helper selects 39 portable
and actual native tests on Windows, with no POSIX test classes selected.

The source/native tests compare process SID bytes against an independent .NET
WindowsIdentity query, test real ImpersonateSelf refusal in a disposable process,
compare handle counts around 64 fresh queries, and check SID boundaries against
native validation. These are wired into the required native CI job from source
and from the installed wheel; they remain pending actual execution.

Fault tests cover fixed-width FFI signatures and system DLL resolution, exact
ERROR_NO_TOKEN semantics, query-only rights, complete handles/SIDs, fresh queries,
both impersonation checks, cleanup and allocation failures, sizing bounds,
unexpected sizing success, one growth retry, null/outside/short pointers,
malformed SID and native length/validation disagreement. Inert import is checked
in clean processes. An implementation pass plus fault/FFI and artifact passes
added distinct evidence; no independent review is claimed.

Logs stay outside Git at `/private/tmp/mos-windows-principal-static.log`,
`/private/tmp/mos-windows-principal-wheel.log` and
`/private/tmp/mos-windows-principal-final-check.log`. Documentation links and the
required native CI dependency were checked; the final diff is whitespace-clean.
No principal-code changes followed the frozen gate; documentation closeout gets link/diff
checks rather than another unchanged full run. Existing identity selectors,
consumers, serializers and storage policy are unchanged from 9285c56.

Stop reason: local implementation/fault/FFI/artifact gates passed; the native
portions of P-02/P-03/P-05 and I-06/I-08 remain pending actual Windows evidence and
accountable boundary review. At local verification closeout this branch was
uncommitted and unpublished; no
selector admission, native qualification, merge or release is claimed. Contract,
plan, roadmap, proposed ADR and the existing platform memory key are updated.
The next publication step is commit/review and source/wheel native CI; actual
candidate version/architecture results must be recorded before admission.
The next implementation slice is
local-NTFS opened-file identity. Native qualification must precede selector
admission; migration/adoption remains a separately reviewed batch.

## Publication integration

Implementation commit 05ffa13 records the locally verified principal batch. Parent
PR #264 merged before publication. The branch incorporates GitHub `main` at
b3546f9, including dependency/Anthropic transport PR #265 and its diff-render
fixture repair. The merge was conflict-free; principal runtime and tests remain
byte-identical to 05ffa13.

On the integrated tree, lint, formatting, strict typing, runtime-export verification
and source/wheel builds passed with the new locked dependencies. Focused source
checks collected 55 platform tests (51 passed, four actual Windows cases skipped),
11 Anthropic provider tests and four conversation diff acceptance tests (all passed).
A fresh wheel-only environment again collected 55 platform tests with 51 passed
and four native skips. Logs are `/private/tmp/mos-windows-principal-main-static.log`,
`/private/tmp/mos-windows-principal-main-tests.log` and
`/private/tmp/mos-windows-principal-main-wheel.log`.

The full combined `make check` result above applies to 05ffa13 before integration.
A second full suite was not run after integrating main; the affected checks passed.
Remote Ubuntu full-source/package and native Windows source/wheel qualification
remain pending CI. This publication preparation does not admit the public Windows
selector or grant native qualification, merge, release or storage authority.

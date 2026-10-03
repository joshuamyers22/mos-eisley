# Tagged identity values and POSIX queries

Status: local implementation verified; native CI pending. Owner: Josh Myers. Started: 2026-10-03.
Base: 23a8b0a, initially clean `feat/platform-identity-posix` worktree.

Objective: implement the first additive step of
[the identity contract](PLATFORM_IDENTITY_CONTRACTS.md): strict tagged values,
borrowed references, real POSIX queries and explicit Windows refusal. Existing
consumers, retained codecs/bytes/hashes and private-storage policy remain intact.
No native token/handle adapter, migration, privileges or dispatch is added.

Selected guidance: [Python guide](PYTHON_ENGINEERING_GUIDE.md),
[verification guide](AGENTIC_VERIFICATION_GUIDE.md),
[verification template](../templates/AGENTIC_VERIFICATION_LOOP.md),
[work-note template](../templates/WORK_NOTE.md), and the existing
[identity threat model](PLATFORM_IDENTITY_THREAT_MODEL.md) and
[ADR-0014](adr/0014-platform-identity-contracts.md).

Blocking rubric: I-01–I-05 and the additive I-09 compatibility boundary; strict
noncoercing construction, inert import, typed failure with causes, one fstat sample,
no pathname lookup, unchanged borrowed descriptor lifetime/offset, uncached real UID
and mismatch refusal, source and installed-wheel packaging. Actual native refusal
CI remains pending publication; I-06–I-08 remain future native-adapter gates.
Risk: material identity boundary. Ceiling: three material correction passes and
four hours of active work; long existing quality gates recorded separately. Stop
when focused evidence and one frozen `make check` pass; reproduce failed gates
without weakening unrelated fixtures. Domain review is required before native
qualification or consumer/schema adoption, not claimed by this implementation.

## Evidence and handoff

| Evidence | Result |
|---|---|
| Isolated source identity tests | 20 passed; strict values/widths/tags, malformed/mutable input, inert import with missing POSIX APIs and DLL-interface import guard, context/refusal and real descriptor cases |
| Reader plus identity from fresh wheel-only environment | 30 passed; both modules verified inside the new environment, inherited PYTHONPATH removed, no CLI/runtime dependency import |
| Focused existing conversation/memory/SQLite/guidance tests | 22 + 17 + 15 + 16 = 70 passed |
| Nine existing state/storage/codec/wrapper modules compared with 23a8b0a | Byte-identical; no consumer, serializer or schema adoption |
| Native-required helper guard and CI dependencies | Guard exited 2 on macOS as required; scoped native job still required by quality and now selects 14 portable reader/identity tests |
| Frozen combined `make check` | Exit 0: lint/format, strict typing, 2,672 source tests in 2,222.611 seconds (four existing skips), 86% coverage, runtime export, builds and 1,948 installed-wheel tests in 1,459.074 seconds without skips |

Each observation is scoped to macOS local execution. Ubuntu and native Windows CI
for this branch remain pending publication. Simulated refusal and portable binary
SID validation do not qualify native TokenUser, impersonation, NTFS handle queries
or SID validation against the native API. I-06–I-08 remain open. I-09 evidence is
additive source/wheel compatibility and unchanged existing codecs/checks; no owner
rebinding, migrated schema or cross-host replay has been tested or authorized.

## Decisions and closeout

- Runtime dataclasses retain full identifier widths and fixed tags; reprs omit
  payloads. Borrowed references are distinct and range-checked. Arbitrary integers
  and reference subclasses cannot substitute for the exact defined query inputs.
- POSIX principal queries are fresh and refuse real/effective UID mismatch. OS
  failures preserve causes behind safe typed messages. Object queries use one fstat
  sample, reject nonregular/nondirectory objects and never take caller ownership.
- Real duplicate descriptors, hardlinks and rename preserve identity; a separately
  held replacement differs. Offset/inheritance remain unchanged; content mutation
  demonstrates that identity is not a digest or immutable snapshot.
- Existing ownership/mode/link/lock/hash checks remain in place. New APIs are not
  adopted by consumers. No runtime dependency, codec, credential or authority change
  is introduced. Native admission and migration require their own reviewed batches.
- Stop reason: local blocking rubric passed. No further code changes followed the
  frozen gate. Documentation closeout gets link/diff/format checks rather than
  another unchanged full-suite invocation. Disposable logs stay outside Git at
  `/private/tmp/mos-platform-identity-check.log` and focused logs in the same folder.
- Contract, plan, roadmap and the existing platform memory key reflect this additive
  implementation; ADR-0014 remains proposed for native qualification/adoption.
- This batch is recorded on `feat/platform-identity-posix`, based on the identity
  definition commit 23a8b0a and reader PR #258. No push, PR, merge or release was
  performed. Parent publication/rebase and required remote CI must be resolved
  before merging. Next step: publish and review this bounded batch; native
  read-only identity adapters are the next implementation slice.

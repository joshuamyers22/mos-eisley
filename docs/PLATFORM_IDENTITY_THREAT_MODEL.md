# Principal and file-identity boundary threat model

## Scope and ownership

Owner: Josh Myers. Date: 2026-10-03. Baseline: f8a8e94. Review trigger: implementation
of [the defined identity contracts](PLATFORM_IDENTITY_CONTRACTS.md), native adapter
admission, or consumer/schema adoption. This is design preparation; accountable
boundary review and native qualification remain pending.

In scope: identifier inputs, OS token/descriptor observations, native query buffers
and borrowed/temporary handle lifetime. Out of scope: implementing DACLs, secure
namespace opens, writes/locking/durability, migration, provider calls or execution.

## Assets, actors and boundaries

| Asset | Need | Boundary |
|---|---|---|
| Retained owner and file observations | Correct interpretation; no unauthorized rebinding | Untrusted retained input versus validated local OS observations |
| Live caller-owned references | Remain usable, correctly typed and unclosed by queries | Borrowed fd versus HANDLE; ownership/lifetime stays with caller |
| Temporary token handles and buffers | Bounded allocation, safe pointer access and cleanup | Native API/FFI versus owned Python values |
| Legacy snapshots and receipts | Byte/hash preservation | Additive values versus existing codecs and SQLite metadata |

Actors include a local path-replacement adversary, malformed identity input, stale
or closed-reference callers, and a changed/impersonating security context. Kernel
observations assume the selected OS is trusted; malicious administrator/kernel
behavior is outside this primitive's isolation guarantee. No new external service
or third-party runtime dependency is proposed. SID/UID values can identify people;
routine logs must omit them. This metadata confers no authorization.

## Abuse cases and controls

| Abuse | Consequence | Required control/evidence | Residual limit |
|---|---|---|---|
| SID/RID/UID or device/volume conflation | Wrong owner/object comparison | Tagged strict values, full-width equality, I-01 | Same numerical UID across hosts is still not authenticated common scope |
| Environment spoofing or impersonation fallback | Wrong current principal | Native OS queries only; mismatch/impersonation refusal, I-03/I-06 | Context can change after a query; effect boundary must revalidate |
| Path substitution between stat/open | Identity attached to a different object | Query only supplied live reference, I-04/I-07 | Query does not qualify the original path admission |
| Reused inode/ID or fd number | Stale observation accepted | Compare while original references remain held; never admit from stale values, I-04/I-05 | Value alone has no permanent lifetime or content guarantee |
| Hardlink or unchanged-ID content mutation | Privacy/integrity falsely inferred | Keep link/permission/DACL and digest policy separate, I-09 | Same-object equality intentionally accepts aliases |
| Truncated native ID or malformed SID pointer | Collision or memory fault | Full-width layout, bounds before native SID validation, I-01/I-06/I-07 | Native ABI/layout must be validated on each advertised architecture |
| Query failure treated as missing/zero identity | Unsafe continuation | Typed explicit error, no synthetic fallback, I-05/I-08 | Caller must preserve refusal in its own error path |
| Unbounded native sizing or leaked token handle | Resource exhaustion | 64 KiB allocation ceiling, bounded retries and cleanup tests, I-06/I-08 | Hosted CI alone cannot cover every privilege/storage configuration |
| Query closes/reopens borrowed reference | Wrong object, offset or use-after-close | Never close, read, reopen or mutate caller reference; I-04/I-05/I-07 | Caller must prevent concurrent close/reuse |
| New value serialized into old artifact | Invalid hashes/rebinding | Keep codecs/writers unchanged; exact legacy fixture evidence, I-09 | Future persistence requires its own accepted migration contract |

## Decisions and recovery

No new accepted privacy or authorization exception is granted. Equality is
contextual metadata. DACL/permission admission, namespace containment and privilege
policy remain separate responsibilities; their native implementations are open.

Implementation must retain independent native principal/file-ID oracle tests,
negative/fault tests and source/wheel compatibility checks. Any unavailable native
case is reported as pending, not passed. Native API behavior, account scope or
schema semantics that cannot meet the contract trigger a separate reviewed design.

Before adoption, rollback removes additive modules and CI/tests without rewriting
artifacts. After adoption, migration/recovery dependencies must be reviewed in the
following schema batch. These records contain no credentials, retained private
payloads or new dispatch authority.

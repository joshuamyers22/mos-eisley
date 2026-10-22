# Session recovery threat model

- System: plan §31.4 implementation on `feat/session-recovery`, based on 81134e0
- Owner: Joshua Myers; implementation review is agent-authored engineering evidence
- Date: 2026-10-21; revisit on journal schema, tool continuation or sandbox changes
- Scope: durable controller intent/results, restart, dispatch guard and container recipe
- Outside scope: release acceptance, new provider authority, external billing,
  compromised same-UID host/Docker daemon, Windows qualification, study evidence

## Assets and boundaries

| Asset | Integrity or privacy requirement | Existing owner/boundary |
|---|---|---|
| Session intent, steering, admitted request, result | Exact owner/workspace and verified retained payload | Private snapshot/SQLite store and held writer lock |
| Consumed attempts and resource exposure | No reset, refund or duplicate dispatch during recovery | Session goal/branch records and separate transactional spend ledger |
| Dispatch decision, terminal event and cursor | One transaction; monotonic identity and sequence | Existing session publication boundary |
| Source revision and tools | No changed workspace or capability before dispatch | Trusted workspace observer, tool policy and task-local guard |
| Disposable worker | Exact image/recipe, scoped input, no host mounts or network | Trusted host broker, Docker daemon and cancellation-safe guardian |

Model/tool output and retained conversational content are untrusted. A session
checksum establishes local integrity, not authorship or new execution authority.
The recovery journal contains only bounded identity/digest metadata; original
payloads stay in their existing bounded stores.

## Abuse and failure cases

| Case | Control | Evidence and residual limit |
|---|---|---|
| Lost dispatch acknowledgement causes replay | Persist decision/attempt first; reopen as uncertain | Real-store dispatch-ack matrix; conservative false uncertainty is intentional |
| Lost result acknowledgement loses completed work | Commit result and terminal event/cursor together | Real-store result-ack matrix; verified reopen retains completion |
| Process/sandbox loss erases steering or budget | Recover existing session, never sandbox transcript | Abrupt subprocess exit and child recovery; queued steering keeps its ancestry |
| Uncertain paid call gets a fresh budget | Preserve original ledger identity and full unresolved hold | Real SQLite spend-ledger test with synthetic runner; actual provider billing is unverified |
| Corrupt/reordered/duplicate events advance cursor | Typed version, contiguous sequence, unique operation, session ID/revision and result bindings | Negative journal tests plus existing storage hashes; trusted-host rollback remains possible |
| Foreign owner/workspace opens retained state | Existing storage/lock/identity checks precede controller construction | Both-store owner/workspace negative tests |
| Replacement changes mounts/image/capabilities | Freeze recipe, persist child recipe digest, compare before execution/integration; inspect immutable image/implicit volumes and exact argv | Drift, commit-race and both-store recipe-retention tests; Docker daemon remains trusted |
| Workspace changes during creation or between calls | Guard before every model/tool call and container create/start; dependent broker/source checks remain | Actual tool-loop and controlled-container tests; host filesystem is trusted between observations |
| Cancellation abandons worker or retries effects | Existing owned cleanup is awaited; operation closes uncertain | Async broker repeated-cancel/cleanup and child/live coding regressions |
| Metadata growth exhausts storage after effects | Fixed 96-event bound and existing session/header size admission before dispatch | Existing byte-limit/storage suites; oversized candidates visibly refuse |
| Older binary drops new recovery evidence | Strict unknown-field rejection; retain compatible reader and backup | Legacy-default round trips; old-reader downgrade is deliberately unsupported |

## Disposition

No new secret, network destination, publication or approval bypass is introduced.
Engineering checks exercise controlled dependencies and real local stores/processes;
they do not constitute independent security or release acceptance. Any future
partial tool-loop resume, mounted worker, retry or reconciliation path must revisit
this threat model and its authorization/idempotency contract before activation.

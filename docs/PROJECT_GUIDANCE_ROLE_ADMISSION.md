# Current role-context admission

`mos guidance-context check` checks a frozen packet against the exact current
project, role, scope, context digest, combined assessment and explicitly selected
private owner policy. Historical `show` remains available after project updates;
a successful historical read cannot satisfy this current check.

```sh
mos guidance-context check -C /path/to/project \
  --snapshot-sha256 SNAPSHOT_HASH --context-sha256 CONTEXT_HASH \
  --role coder --scope 'Implement batch execution' \
  --policy /path/to/private/policy.json \
  --expected-policy-sha256 REVIEWED_POLICY_HASH --json
```

Use hashes from a reviewed [frozen packet](PROJECT_GUIDANCE_ROLE_CONTEXT.md).
Role and scope must match exactly, including whitespace. Check is read-only and
returns metadata without rule text or private policy prose. Failure returns nonzero.
The result describes the instant of inspection; it is never a reusable permission
or admission token. A later consumer must revalidate.

## Guarded local consumption

Python consumers can use `RoleContextAdmissionStore.guard_context` with a typed
`RoleContextSelection` and explicit workspace/policy inputs. It reconstructs the
snapshot from retained immutable evidence, checks exact selection and current
complete assessment/policy, then yields only the bounded `RoleContext` under the
private guidance lock. It rechecks identities and source contents before yielding
and after successful local use. Ordinary guidance writers cannot change the
selection while this guard holds the lock.

Use the guard only for short local payload preparation. Do not dispatch providers,
wait for user input, or recursively acquire the guidance lock inside it. External
filesystem edits are detected by final validation, but validation cannot roll back
side effects already performed by a caller. Caller exceptions propagate and release
the lock. Retained policy bytes support historical reconstruction only; current
admission always opens the explicitly selected private policy and checks its hash.

Any assessment revision, requirement clear/reaccept, changed binding or override,
unresolved conflict, changed policy bytes, missing/corrupt snapshot or mismatched
owner/project rejects. Even a new allowed policy hash requires a newly reviewed
freeze. No implicit refresh, raw brief reread, transcript import or stored-path
follow occurs. Existing 64 KiB context and private single-link file limits apply.

This slice supplies the current local consumption boundary. Wiring it into an
actual role run, pinning packet hashes in that run's manifest, enforcing total
request budgets and rechecking before dispatch remain subsequent work. Guidance
text does not grant model, tool, spend or containment authority. It does not
semantically evaluate policy prose or choose the user's authoritative policy.

This additive command/API creates no new persistent state. Rollback leaves all
frozen packets and historical inspection available.

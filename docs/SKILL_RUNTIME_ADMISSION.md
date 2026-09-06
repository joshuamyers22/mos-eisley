# Guarded skill runtime broker admission

Mos Eisley can now turn one prepared skill request into one durable broker-admission
record without sending it. Admission reverifies the complete empirical routing lineage
and complete skill lineage, requires the exact current routing and skill control
anchors, current default pointer, and exact held spend reservation, then commits one
immutable record to a separately pinned private store.

This is readiness evidence, not provider-dispatch authority. No bearer capability,
credential, provider token count, network connection, response, settlement, retry, or
budget release is created.

## Signed and local bindings

Runtime-authority policy schema version 2 additionally pins:

- the routing activation-authority policy;
- the routing control-anchor policy; and
- the exact admission-store policy.

The admission-store policy is created before the runtime policy is signed. It pins one
store identity, routing control anchor, skill release-control anchor, default store,
and spend ledger. This avoids a cyclic hash while preventing a different store policy
from accepting the signed request. Copying or rolling back the same store identity
remains an external monotonic-state problem.

The admission record binds the prepared request and signed decision, runtime request,
routing preflight and latest routing-control entry, latest skill-control entry, default
pointer, normalized provider request, broker request, spend ledger, ledger entry, and
reservation. It contains hashes and amounts but no prompt, user input, provider
credential, or capability.

## Commit boundary

Before admission Mos Eisley reconstructs both evidence graphs. Routing verification
recomputes calibration, frozen policy, one-use holdout, promotion, three independent
operational signatures, eligibility, and the exact runtime preflight. Skill
verification recomputes promotion, release, current control, installation, default,
post-selection health, exact retained prompt bytes, runtime signature, request, route,
and spend binding.

Across the admission-store commit, read locks hold:

- the exact latest routing activation control;
- the exact latest skill release control;
- the exact current skill default pointer; and
- the exact existing held spend-ledger entry.

The admission store then inserts one deterministic identity with unique constraints on
the prepared request, decision, and ledger entry. It does not insert into the spend
ledger, so the aggregate charge and entry count are unchanged. A duplicate admission
fails closed. A database failure rolls back the admission while leaving the existing
reservation held and the earlier runtime authority consumed.

```console
mos skill-runtime-admission-store-create \
  --path private/runtime-admissions.sqlite \
  --admission-store-policy trusted/runtime-admission-store-policy.json \
  --routing-control-anchor private/routing-control.sqlite \
  --skill-control-anchor private/skill-control.sqlite \
  --default-store private/skill-default.sqlite \
  --spend-ledger private/spend.sqlite

mos eval-admit-skill-runtime-request \
  --prepared-runtime-request private/prepared-runtime-request.json \
  --admission-store private/runtime-admissions.sqlite \
  --output private/runtime-admission.json \
  ...the exact runtime, routing, skill, and spending sources...

mos skill-runtime-admission-status \
  --prepared-runtime-request private/prepared-runtime-request.json \
  --admission-store private/runtime-admissions.sqlite \
  --spend-ledger private/spend.sqlite
```

Status is read-only and reports whether admission is absent or committed plus the
current ledger state. It always denies retry, broker-grant authority, provider
dispatch, and automatic budget release.

## Deliberate limits

An admission does not authorize the next process to send. Independent explicit
[dispatch authority](SKILL_RUNTIME_DISPATCH_AUTHORITY.md) can now be consumed exactly
once under fresh guards, but its durable claim is still not a bearer. A later exchange
must mint one short-lived request-bound capability. Immediately before the first
provider interaction it must recheck both current controls and the held
reservation, persist the ambiguous-send boundary, locally or provider-count input
tokens, and settle response, rejection, timeout, cancellation, and lost-response
states conservatively without retry.

Locks are released after the local admission commit. Holding revocation locks across a
network request would delay emergency control changes, so later dispatch must define
how a control advance between admission and send fails closed. Local clock integrity,
database copying/rollback, signer custody, same-UID access, provider behavior, and
invoice reconciliation remain trusted boundaries.

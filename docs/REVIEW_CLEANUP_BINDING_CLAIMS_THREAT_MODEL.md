# Threat Model: retained cleanup binding claims

## Scope and ownership

- System/version: sealed formal terminal cleanup at `326dafe`.
- Owner and reviewer: Joshua Myers.
- Date and trigger: 2026-09-23; mutable-binding, campaign-ID and terminal-window
  findings from the latest formal campaign.
- In scope: public binding mutation, sealed campaign identity, terminal seal reread
  and original start-window boundaries.
- Out of scope: arbitrary trusted-process private-state mutation, provider behavior,
  retries, historical evidence changes and live activation.

## Assets and trust boundaries

| Asset | Integrity need | Boundary/control |
|---|---|---|
| Retained slot selection | Directory, seal pin and slot cannot change in place | Frozen scalar contract plus canonical ownership copies |
| Campaign identity | Exact campaign bytes must be independently identified | SHA-256 pin of seal bytes; seal binds bundle and policy digests |
| Deferred judge allowance | Retirement only for an admitted start in the original window | Terminal reread, exact slot comparisons and start-window predicate |
| Terminal marker | Must not claim cleanup when admission fails | Retirement boolean reflects only an actual ledger transition |

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Controls/evidence | Residual risk |
|---|---|---|---|---|
| Caller mutates an exposed binding | Public reference to controller binding | Redirect cleanup to another seal or slot | `Contract` is frozen; binding fields are scalar; controller/probe/admission own canonical copies; assignment probe fails | Privileged code can replace private attributes and is outside the process boundary |
| Human label is substituted as campaign identity | Ambiguous “campaign ID” wording | Wrong campaign accepted | Independent seal digest is the sole content-addressed identity and binds complete bundle/policy bytes | Future review briefs can recreate confusion unless terminology is corrected |
| Bundle changes after controller start | Writable local campaign directory | Stale admission retires capacity | Terminal rereads the pinned seal; post-start key-loader and after-generation tests assert hold preservation | Local tampering can deny cleanup and leave a conservative hold |
| Controller start is outside original window | Expiry race or malformed internal state | Capacity retired outside committed authority | Cleanup predicate plus direct pre-seal and exact-expiry terminal regressions preserve the held allowance | Privileged private-state mutation remains outside the process boundary, but cannot satisfy this cleanup predicate |

## Decisions

- Do not add a redundant campaign identifier. Treat the independently retained seal
  digest as the campaign identity and use that exact term in future specifications.
- Do not change binding runtime code in response to the mutable-binding claim.
- Existing post-start seal-tamper tests satisfy that terminal claim.
- Direct terminal regressions now cover a start before `sealed_at` and a start exactly
  at the earliest committed expiry. Both preserve the held allowance, record
  `unused_judge_allowance_retired=false`, and make no judge call.

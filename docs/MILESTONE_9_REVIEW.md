# Shared-spending ledger adversarial review

Scope: a provider-neutral local ledger plus integration into the one-prompt CLI.
No live evaluation, paid request, new provider or automatic routing is enabled.

| Failure or attack | Implemented defense | Residual boundary |
| --- | --- | --- |
| Workers race on remaining budget | One immediate transaction checks sum and inserts reservation | Tested with separate processes; local filesystem locking is trusted |
| Process dies after admission | Committed held amount survives abrupt exit | May strand capacity even when no call occurred; intentionally no automatic refund |
| Reservation/settlement is replayed | Unique run-derived identity, hash binding and held-only transition | Caller/database owner remains trusted |
| Unknown response is treated as free | Full uncertain exposure retained | Provider billing can only be reconciled manually |
| Provider violates priced assumptions | Committed violation blocks further ledger admission | In-flight calls persist; crash before classification can leave held state |
| DB absent or accidentally replaced | Explicit exclusive creation, open-existing only, immutable policy checks | A fresh process cannot detect a restored/copied or maliciously rewritten ledger |
| Disk full or lock contention grants admission | DB failure prevents generation; settlement failure retains exposure | Database and receipt are not a distributed transaction |
| Receipt write fails after settlement | Manifest absent; settled ledger still accounts for known usage | Output completion and cost settlement are distinct |
| Private material leaks into shared accounting | Only hashes, amounts and state stored in private database | Trusted ancestors and same-UID host processes |
| Local control is mistaken for account cap | Explicit scope and documented exclusions | Other clients/ledgers and unpriced fees are outside scope |

Validation includes concurrent process admission, committed reservation after
abrupt exit, lock contention, duplicate and malformed settlements, fail-closed
file handling, CLI creation/status, and fixture-transport settlement failures.

Next: isolated executor and trusted broker that keep labels and host secrets out of
backend reach while sharing this ledger. Verify containment with negative tests
before enabling paid sweeps; a plain subprocess is insufficient.

# Shared local spending scopes

The explicit `openai-run` command now requires both a per-request pricing policy
and an existing shared ledger. This closes the gap where concurrent invocations
could each fit a per-request ceiling while exceeding a common budget. It does not
enable live evaluation, and does not cover API calls made outside that ledger.

Create a scope once in a trusted, existing local directory, then reuse its path for
every participating invocation:

```sh
uv run --frozen mos spend-ledger-create spending.sqlite --ceiling-microusd 5000000
uv run --frozen mos spend-ledger-status spending.sqlite
uv run --frozen mos openai-run --prompt prompt.txt \
  --spend-policy spend-policy.json --spend-ledger spending.sqlite \
  --allow-data-transfer --json
```

The example authorizes $5 of generation-token exposure across participating runs;
it is a budget choice, not a pricing quote. [Reviewed prices](OPENAI_SPENDING.md)
are still required. Creation and status commands emit JSON and never contact a
provider. Existing files cannot be overwritten; opening a missing or malformed
ledger fails instead of creating an empty replacement. Parent directories are not
created or made private automatically; the database itself is created mode 0600.

## State and transaction rules

Admission serializes the sum check and reservation insertion with SQLite
[`BEGIN IMMEDIATE`](https://www.sqlite.org/lang_transaction.html). Each connection
requires rollback journaling and requests
[`synchronous=EXTRA`](https://www.sqlite.org/pragma.html#pragma_synchronous).
The transaction commits **before** the response call. No database transaction is
held across provider I/O. A lock wait of more than 250 ms fails closed; there is no
application-level retry. These guarantees assume a working local filesystem and
SQLite locking/sync support, not arbitrary hardware or network filesystems.

| Entry state | Contribution to charged total | New admission |
| --- | --- | --- |
| `held` | Full reserved maximum | Remaining capacity only |
| `settled` | Validated usage at reviewed rates | Remaining capacity, including known savings |
| `uncertain` | Full reserved maximum | Remaining capacity only |
| `violation` | Full reserved maximum, not a proven bill bound | Entire ledger blocked |

A zero-cost settled response is allowed, but its entry identity cannot be reused.
Unknown entries, mismatched reservation hashes, duplicate admission/settlement,
amounts above the reservation and partial release of uncertain exposure fail.
There is no expiry of a held reservation, manual release, top-up, reset or resume
command. Already-admitted requests may still complete after another run records a
violation; blocking prevents new admission, not cancellation of in-flight work.

Status reports charged and available micro-USD, total and unresolved entry counts,
the immutable scope identity/ceiling, and whether the scope is blocked. A blocked
scope can show positive available arithmetic headroom; that is not authorization
to spend. Identity and ceiling are rechecked on every transaction against the
opened ledger object.

## Failure ordering and audit

The local reservation artifact is file-fsynced first, followed by shared admission.
If either fails, no generation starts. A reservation artifact without a ledger
entry can therefore describe a denied attempt; do not infer a provider call from
its existence. If a process exits after admission, the ledger keeps its full held
amount even if the process never reached the provider. No automatic recovery
assumes that a missing response means zero spend.

After validating a response, the controller settles the ledger before writing its
private receipt. Ledger settlement failure leaves exposure held and the run fails;
receipt failure after settlement can leave the ledger settled without a completed
run. A complete manifest remains the marker for successful agent output. Receipts
include ledger and entry identities; entry IDs hash the absolute run-directory
path, and ledger rows retain the reservation hash. Paths, prompts, responses and
credentials are not stored in the ledger. Moving a run does not rewrite its entry.

The ledger and artifacts are not one atomic transaction. A crash or disk error
before violation classification is committed can leave that entry merely held,
not globally blocked. This conservatively preserves reserved exposure, but cannot
guarantee an actual bill ceiling if the provider has violated pricing assumptions.
Keep failed-run artifacts for manual investigation; do not rerun an uncertain
request assuming its earlier reservation was refunded.

## Trust boundary and remaining work

Use one ledger for one operator-chosen spending scope on one host. Copying,
restoring, deleting/recreating or choosing a different ledger creates independent
accounting and can bypass the intended aggregate limit. No anti-rollback service,
authenticated broker, signed receipt or cross-host synchronization exists. A
same-UID actor who can modify the database is trusted. This authoritative ledger
is **not** the rebuildable review-run SQLite index.

Rates, service-tier and output-count contracts remain assumptions; taxes, fees,
token-count endpoint charges and external account traffic are not included. The
OpenAI Docs skill confirmed that the documented
[output cap includes reasoning tokens](https://developers.openai.com/api/reference/cli/resources/responses/methods/create),
so aggregation retains the existing single-count accounting. No new live API
contract or credentialed capability has been established.

The lower-level transport keeps optional ledger support for legacy/fixture callers;
the CLI requires it. Historical per-response artifacts remain inspectable but do
not establish shared-budget participation. Still required before empirical live
sweeps: a label-isolating execution boundary, trusted ledger/credential broker,
bounded HTTP buffering and explicit credentialed conformance. Automatic difficulty
routing remains disabled pending held-out quality, latency and cost evidence.

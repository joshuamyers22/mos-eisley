# Milestone 38 adversarial review: runtime response publication

## Disposition

Accepted as an atomic, locally content-verified publication of one exact settled
provider response. Rejected as external proof of provider authorship, invoice
finality, global uniqueness, or containment from malicious code under the same user.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| A valid transaction is published through a substituted store | Transaction-policy schema 2 pins the complete response policy, and that policy pins the transaction-store ID | Owner-controlled database cloning or rollback needs an external witness |
| Many individually valid records exhaust local storage | Policy caps individual raw/result payloads, aggregate raw retention, and record count before each commit | SQLite metadata overhead and owner-controlled filesystem exhaustion remain external |
| A response is changed after settlement | Publication recomputes canonical response bytes and requires the exact response digest recorded by the settled outcome | A malicious trusted transport can fabricate the original bytes |
| A result is invented independently of provider content | The compiler parses the retained response, and store writes and reads repeat exact ID, stop, usage, model, and assistant-text comparison | Parser and trusted code correctness remain in the trusted base |
| Reasoning or encrypted state leaks through the result | Published turns are text-only; reasoning stays in the private raw record and regression tests scan CLI output | Same-UID filesystem/process access remains trusted |
| A tool call is presented as ordinary assistant text | Tool-bearing and reasoning-only responses are rejected, even after spend settlement | Such responses remain privately accounted but require separate handling policy |
| One outcome is published twice | Unique transaction, outcome, request, publication, and result identities plus explicit replay rejection | Copied or rolled-back stores are not globally coordinated |
| Publication partially commits | Raw response, result, manifest, intent, and outcome share one rollback-journal transaction with `synchronous=EXTRA` | Filesystem, controller, and hardware durability remain trusted |
| Stored rows or indexes are edited | Every status/load verifies canonical forms, hashes, row columns, lineage, and result-to-response equivalence | A same-process attacker can replace code as well as data |
| Publication failure changes spend or authorizes retry | Settlement happens before publication; injected failure leaves settled spend unchanged and both retry/release remain false | Manual retention/reconciliation policy is not implemented |
| An operator command exports private response bytes | CLI provides only create, verified count, and reasoning-free result operations | Direct owner filesystem access is deliberately outside the CLI boundary |
| A text result is described as credential-free | The boundary promises only that it accepts and adds no provider credential; model text remains explicitly untrusted | Output-content classification and redaction require a separate policy |

## Follow-on requirement

Run separately authorized credentialed OpenAI conformance through the exact
zero-retry transaction and publication boundary. Record provider/account observations
without treating one paid call as model-quality evidence, and add external billing or
monotonic witnesses before making stronger cross-process or cross-host claims.

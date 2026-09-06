# ADR 0002: Canonical agent protocol before live providers

Date: 2026-09-05. Status: implemented for the offline fixture milestone.

## Decision

Introduce a provider-neutral request/response protocol before adding any vendor
SDK. The canonical protocol owns user and assistant turns, text and reasoning
blocks, tool calls/results, usage, stop reasons, tool schemas and effort levels.
Provider-native IDs and opaque reasoning may be retained as bounded metadata, but
vendor wire types do not cross the adapter boundary.

Validate whole histories, not only individual blocks. Requests must begin and end
with user turns, alternate roles, use globally unique harness call IDs, and return
exactly one matching result for every pending call. Assistant responses must align
their stop reason with tool-call presence. Contracts are strict, immutable,
versioned and canonically serialized.

Use an explicit registry as the authority for model capabilities. Unsupported
effort requests fall only to the nearest lower supported level and report that
substitution; they never silently escalate. Until provider tokenizers and pricing
are verified, enforce serialized-byte budgets and label their unit accurately.

Bound the loop by iterations, tool-call count, provider deadline, tool deadline and
request/result bytes. Cooperative cancellation propagates. Record request,
response and tool boundaries to an append-only, mode-0600 JSONL journal, fsyncing
each event. Journals contain status and canonical payload hashes; run inputs,
cassette and result supply the replay content. A manifest is the completion marker.

Ship only a pure, bounded in-memory lookup tool and a request-hash-bound recorded
model adapter. This exercises orchestration without granting filesystem, process,
network, Git or credential capability.

## Consequences

The agent loop and replay semantics can be tested deterministically before privacy,
cost and containment risks enter the system. A live adapter must prove canonical
round-trip behavior and translate its tokenizer/context limits rather than assuming
byte counts equal tokens. Live response persistence will need full redacted content
or an authenticated external recording; the current hash journal alone cannot
resume an interrupted provider run.

The controller still trusts adapters not to block the event loop. Async deadlines
cannot stop synchronous native code. Machine-capable tools remain prohibited until
the sandbox capability matrix and negative suite are implemented.

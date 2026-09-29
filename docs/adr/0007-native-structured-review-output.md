# ADR-0007: Native structured output for capable review models

- Status: accepted
- Date and owner: 2026-09-20, Joshua Myers

## Context and options

The canonical model reviewer currently embeds its result JSON Schema in system
instructions and then applies strict local validation. A live critic nevertheless
returned a duplicate key, consuming one of two critic slots and preventing a
two-critic quorum. The OpenAI conformance path already uses strict `text.format`
JSON Schema, and the model registry explicitly declares structured-output support.

Options are to retain prompt-only JSON, weaken or repair malformed responses, add
automatic retries, or carry an optional provider-neutral JSON Schema constraint in
the canonical request and project it through supporting adapters. Retries or repair
would alter the one-exchange spending and evidence contract, while weakening the
parser would admit ambiguous evidence.

## Decision and consequences

Carry an optional, versioned strict JSON Schema output constraint on
`ModelRequest`. `ModelReviewer` will attach it only when the resolved model declares
structured-output support. The OpenAI adapter will translate it to Responses API
`text.format`. Review prompts retain the schema as defense in depth, and all output
continues through the duplicate-aware local decoder and typed contracts.

Use one recursively strict schema-normalization function for the conformance and
review paths. Preserve schema-1 citation compatibility by removing `source_unit`
before normalization; schema 2 includes it. Requests with no response constraint
retain their existing canonical representation and provider payload.

Every object node is normalized even when its generated schema omits `properties`:
the omission becomes an explicit empty property map. A present non-object
`properties` value is rejected. This keeps the shared helper fail-closed instead of
silently emitting a partially strict object schema.

This adds schema bytes to capable canonical requests and therefore to admission
budgets and request identities. It reduces but cannot eliminate provider failures,
does not establish review quality, and grants no dispatch, spending, qualification,
or retry authority. A future live retest should use three independently admitted
critics with a two-critic threshold so one failed response can be tolerated without
a retry; correlated same-provider failures remain possible.

## Verification

Acceptance requires exact canonical/provider projection tests, recursive strictness
checks, capable/incapable model behavior, schema-1/schema-2 and judge coverage,
unchanged duplicate-key rejection, a deterministic one-invalid-of-three quorum
test that continues through signed observation authentication and retained replay,
and the complete package/container gates. Reconsider if OpenAI changes its
supported JSON Schema subset, if registry capability becomes provider-route-specific,
or if live evidence shows native constraints do not materially improve validity.

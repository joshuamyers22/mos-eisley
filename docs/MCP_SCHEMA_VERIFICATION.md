# MCP schema compatibility verification

Date: 2026-09-09. Branch: `feat/mcp-schema-compatibility`, stacked on OAuth PR #110.

## Objective and stopping gate

Accept useful MCP schemas beyond the canonical provider-neutral subset without
silently dropping validation or widening tool permissions. Invalid arguments must
not reach the server; invalid structured output must not cause a retry.

Gate: semantic comparison against the original JSON Schema validator, bounded
adversarial schemas, real stdio/HTTP calls, existing MCP regressions, strict static
checks, full repository coverage/build and the installed-wheel contract. Stop at
that gate; paid-provider tool execution and additional schema vocabularies need
separate evidence. No new dependencies, paid calls or production data are used.

## Evidence

`tests/test_mcp_schema.py` contains 13 tests, covering local reference expansion,
escaped pointers, `$ref` siblings, deterministic output, source snapshot ownership,
nullable/type unions, anyOf/oneOf/allOf, dictionaries, constants, constraints,
supported formats, explicit wrapper selection and strict JSON parsing. A table of
source schemas and representative values compares compiled acceptance against
`Draft202012Validator` to detect semantic changes; this is regression evidence,
not a proof over every possible schema/value.

Invalid external/file/missing/recursive references, unknown formats/keywords,
regex patterns, unsupported dialects, tuple schemas, oversized collections,
reference expansion and excessive wrapper descriptions fail registration. The
wrapper rejects duplicate keys, nonfinite values, non-object JSON and extra fields.

Actual SDK tools with Pydantic nested models, nullable fields and dictionary
arguments execute over both stdio and HTTP. Three invalid write inputs leave the
server write count at zero; one valid wrapped call produces exactly one write and
returns a locally validated nested result. Optional arguments continue to reach
server defaults when explicitly wrapped. Invalid structured output fails the
session after one submission.

The combined focused MCP suite passed 66 tests with two optional data integrations
skipped. Full repository and installed-wheel results are recorded in the PR.
`tools/smoke_package.py` copies the fixture/tests into a temporary directory and
runs schema and OAuth tests against the installed wheel outside the source tree.
The earlier OAuth PR's quality, container and secret-scanning checks all passed.

## Findings and limits

Primitive-only root unions initially admitted a useless object wrapper; registration
now rejects schemas that structurally exclude object arguments. Reference siblings
are compiled as conjunctions instead of overwriting target constraints. Partial
native lowering reports are discarded when the tool uses a wrapper, so no unmade
closed-object restriction is reported.

The existing timeout fixture intermittently surfaced an SDK cleanup error after
its expected call timeout. Its assertion now covers the entire failed session,
while preserving cancellation and submission-count assertions. It does not treat
cleanup of a failed transport as successful or resubmit a call.

Only documented keywords and four installed format checkers are accepted. Regex,
uniqueItems, conditionals/dependencies, unevaluated rules, remote or recursive
references and unsupported formats remain blocked. Structural/byte limits bound
this application path; they are not a hard CPU/process sandbox. Wrapper descriptions
are bounded and never truncated. Native closed-object narrowing is retained and
reported; a JSON wrapper preserves the original schema's object-key rules.

The canonical provider schema contract is unchanged. Forced wrappers use one
required string field, but live provider conformance and model performance on
embedded schemas were not tested. No paid tool workflow is enabled.

References: [JSON Schema references and structure](https://json-schema.org/understanding-json-schema/structuring),
[jsonschema validation and formats](https://python-jsonschema.readthedocs.io/en/stable/validate/).

# G1 work-unit-owned profile acquisition

Status: implemented on 2026-09-21. This completes the remaining G1 profile
acquisition seam described in plan §26.4. It grants no tool, execution, credential,
network, spending, or approval authority.

## Durable ownership

A schema-2 task-state bundle may bind a `WorkUnitRecord.task_profile_id` to one
profile assessment in the same private, content-addressed archive. The manifest must
name the exact work-unit ID and revision and the same trusted policy digest. An
acquisition-ready schema-2 assessment retains the exact selected instruction bytes
in manifest order and reproduces their UTF-8 sizes and SHA-256 digests. Its offline
diagnostic report must reproduce and must not fail.

When runtime continuation is enabled, every advertised checkpoint next action must
own such a profile. A missing profile, wrong work-unit revision, changed policy,
failed diagnostic, reordered instruction, or substituted content rejects the bundle.
Unselected profile candidates remain diagnostic data and cannot become runtime
inputs merely by being present in the archive.

Schema-1 bundles remain readable without backfill. A legacy bundle that enabled
continuation before this contract can still be inspected and replayed, but profile
acquisition fails closed until a new schema-2 checkpoint revision explicitly binds
complete material.

## Claim and dispatch

The checkpoint store selects the profile from the claimed work unit; neither the
conversation message position nor the model chooses it. Claim and pre-dispatch
resolution re-open and validate the current checkpoint head, immutable bundle,
workspace, verification inputs, continuation claim, work unit, profile diagnostics,
instruction bytes, and policy binding.

The resolved profile is then admitted against the current trusted tool catalog.
Only selected tools with exact matching schemas enter the request. Stable
instructions and temporary task state retain their separate context classifications,
and reusable memory remains independent.

Schema-6 request admission records text-free acquisition provenance: checkpoint and
bundle revisions/digests, work-unit reference, profile ID/digest, selected
instruction/tool IDs, warnings, and sizes. `/context N` exposes those identities but
never expands private instruction text. The admission is saved before provider
dispatch and cannot be substituted by a later checkpoint or profile revision.

## Failure and recovery

Acquisition failure leaves the message queued, consumes no recorded exchange, saves
no request admission, and does not call the provider. Existing claim idempotency and
checkpoint compare-and-swap behavior remain unchanged. JSON and SQLite conversation
replay preserve the schema-6 receipt; the private checkpoint archive remains the
source for instruction reconstruction.

## Acceptance coverage

Deterministic tests cover exact material acquisition, owned tool selection, private
instruction non-disclosure, schema-6 provenance, JSON replay, legacy replay with
fail-closed acquisition, missing bindings, tampered bytes, stale policy bindings,
workspace changes, duplicate claims, and substituted checkpoint provenance before
dispatch. The installed-wheel smoke suite includes the same continuation tests.

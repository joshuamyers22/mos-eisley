# ADR-0006: Content-bound review citation units

- Status: accepted
- Date and owner: 2026-09-20, Joshua Myers

## Context and options

Review evidence historically required a quote to occur verbatim in the raw `spec`,
`diff`, or `constraints` string. A unified diff encodes every continuation line with
a marker, so exact multiline postimage code is not a raw-patch substring. The final
live test exposed this mismatch: the cited code was supported by one hunk but failed
local validation before quorum.

Options were to normalize patch text during comparison, require models to quote raw
markers, duplicate reconstructed files in every prompt, or define explicit citable
units. Normalization can admit fabricated whitespace or cross-hunk combinations;
raw-marker prompting leaves source semantics implicit; full reconstruction duplicates
large inputs and cannot always reconstruct complete files.

## Decision and consequences

Keep critic-request schema 1 byte-for-byte compatible. Add opt-in schema 2 with a
deterministically derived, bounded catalog of content-bound diff IDs: one whole raw
view and before/after views for each unified-diff hunk. Descriptors contain locators,
not duplicate source text; the original diff remains the readable source. Each ID
includes a SHA-256 binding to its exact view and locator.

Schema-2 diff evidence must name one supplied unit and quote an exact substring of
that unit. The validator recomputes the catalog from the frozen brief, rejects catalog
drift, invented/stale IDs, whitespace changes and cross-unit splicing, and performs no
fuzzy normalization. `spec` and `constraints` retain exact substring validation and
cannot claim a diff unit. Schema 1 retains raw-only behavior so sealed requests and
their outcomes are not reinterpreted.

The catalog adds bounded request metadata and one optional evidence field. It does
not alter provider authority, retries, spending, tools, storage, or judge rules. New
production review preparation uses schema 2; rollback is to stop preparing schema-2
requests, not to rewrite artifacts.

## Verification

Acceptance requires canonical schema-1 compatibility, exact multiline postimage
acceptance in schema 2, fail-closed stale/invented/normalized/cross-hunk cases, bounded
catalog growth, offline retained-shape replay, affected review suites, and full offline
and container gates. Reconsider if another source format needs semantic reconstruction
or catalog metadata materially threatens input budgets.

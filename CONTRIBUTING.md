# Contributing

Group related jobs into bounded review batches. Run focused behavior tests after
each change; immediately test storage, identity, permissions, authentication and
other security-sensitive boundaries when affected. Failed checks block dependent
work until corrected.

Run the full `make check` once on the combined batch before publishing its pull
request. Keep CI quality, secret scanning, dependency auditing and container checks
required before merge. After later code changes, rerun affected checks and validate
the final combined revision; do not reuse stale evidence. Documentation-only follow-ups
need documentation/link checks unless they change an executable contract.

Pull requests must state outcome, risk, verification evidence, and rollback
considerations. Batching reduces redundant full-suite runs, not coverage or gates.

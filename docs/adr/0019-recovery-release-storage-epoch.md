# ADR 0019: recovery sessions require a new release storage epoch

- Date: 2026-10-23
- Status: candidate implementation; accountable release disposition pending
- Scope: rc.8 installation/update metadata and qualification
- Owner: Joshua Myers

## Evidence and decision

Actual published rc.7 resumed neither snapshot nor SQLite sessions written by
the rc.8 source CLI: both exited 2 with `invalid input schema`. The new recovery
journal is intentionally unknown to old strict readers, as already disclosed in
the session-recovery verification record. The release metadata still used epoch 1,
which would incorrectly permit runtime rollback to those incompatible readers.

Sign rc.8 with storage epoch 2. Only explicit retained-release parsing may authenticate epoch-1 metadata,
preserving its actual signed epoch; default candidate/publication parsing remains
current-epoch-only. This is not session-format or installation approval. The new bootstrap only installs its own current epoch.
Existing rollback's equal-epoch guard must reject 2-to-1 before changing the active
pointer or user state. Discovery must not offer a different epoch as a compatible
update. Never strip a journal, rewrite uncertain exposure or merge old/new histories
to satisfy an old reader.

## Consequences and recovery

Use the exact new bootstrap for forward upgrade from rc.7 or earlier; their old
bootstraps correctly reject epoch-2 metadata. Current readers retain legacy-session
support. Before new writes, preserve private pre-upgrade session backups and an
old installation separately. After new writes, retain the epoch-2 reader for those
sessions. An old version may explicitly read the separate pre-upgrade copies;
they do not contain later work. A forward fix is the recovery route for new data.
This is not seamless rollback compatibility, general support or release approval.

Qualification must prove actual predecessor-to-candidate installation, both-store
cold resume and candidate writes, explicit cross-epoch rollback refusal without
pointer/data mutation, interrupted activation recovery, tamper rejection, separate
legacy-backup readability and old-reader rejection of new state. Same-epoch
qualification continues to require successful candidate-written-state rollback.
Reports expose these as separate results, never a blanket rollback success.

The earlier combined gate was interrupted on this evidence-backed finding. Current
focused/full gates and four native signed journeys remain required before the
candidate can be disposed for release.

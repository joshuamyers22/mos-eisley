# Ranked resume discovery work note

Status: complete; implemented and verified. Owner: Josh Myers. Requirement: plan §31.6.
Starting revision: `b090f6b`; clean worktree, branch `feat/ranked-resume`.

Guidance: repository Python engineering guide, bounded verification guide/loop,
work-note template and privacy threat-model template, pinned production template
commit `8879be48f3b760e65f6bed32f8740314fe92910d`.

Objective: deterministic metadata ranking in the existing interactive picker.
Blocking invariants: stronger literal matches precede fuzzy matches regardless of
recency; owner/workspace/storage/backend admission and locked selected-state checks
remain authoritative; no transcript search/cache or automatic session choice.
Exact `--name` ambiguity semantics remain unchanged.

Material correctness/privacy work. Three evidence-changing passes: (1) pure bounded
ranker and contract fixtures, (2) real catalogs, stale selections and terminal
behavior, (3) static/source/installed-wheel gates. Ceiling: three hours of active
work, no paid calls or real owner-data inspection. Stop on passing gates; document
any concrete unresolved failure rather than relaxing authority or test boundaries.

Evidence: ordering and Unicode fixtures, worst-case bounded-work checks, equivalent
JSON/SQLite metadata, real scoped stores, stale rename/deletion/replacement/active
selection, existing keyboard and PTY journeys, and standard `make check -j1`.

Threat model: private session names/IDs and selected-state identity are the assets.
Catalog/storage code admits ownership and workspace; the pure ranker receives
only those summaries. Search input cannot trigger storage reads or select a
session. Invalid/oversized input fails closed, bounded fuzzy matching cannot grow
with transcripts, and final lock/hash/root checks reject stale selections.
Existing JSON catalogs still parse bounded snapshots to obtain metadata; search
adds no snapshot/transcript reads. SQLite uses its existing metadata-only index.

Passes 1–2 complete: 30 focused tests passed (9 ranking/catalog, 6 picker,
11 name/CLI and 4 auxiliary presentation cases). Exhaustive short-string distance
checks agree with an independent full-matrix oracle for one/two edits. A 1,000-row
case-fold expansion fixture exercises the full bounded fuzzy path. Real SQLite
catalogs admit 1,000 sessions without calling state hydration and reject 1,001.
Equivalent JSON/SQLite metadata ranks identically. Two canonical workspaces and
a simulated second UID exercise admission; transcript-only sentinel text never
matches. Search performs no file opens. Keyboard fixtures retain match reasons,
full identity and explicit Enter; real PTY resume restores terminal state and
leaves queued work paused. Both stores reject rename, deletion, changed-state
replacement, directory replacement and new active locks before controller setup.

Decisions: preserve literal ID-fragment discovery beside all-word matches; do not
fuzz identifiers. All-query-word matching retains literal substring behavior.
Fuzzy name matching uses Levenshtein insertion/deletion/substitution, with one
edit for lengths 4–7 and two for longer queries; adjacent transposition costs two.
The saved-time/ID ties are independent of catalog iteration order. JSON catalog
admission retains its existing bounded snapshot parsing; ranking itself adds no
transcript or storage reads. No second index, provider call or new authority.

Pass 3 complete: `make check -j1` exited 0. Ruff lint/format and strict Pyright
passed. The source suite passed 3,823 tests in 2,976.234 seconds (17 existing
skips); total coverage is 85%, above the 84% gate. Runtime export
verification and source/wheel builds passed. The fresh isolated installed wheel
passed 2,790 tests in 2,038.228 seconds (13 existing skips), including
the ranking/catalog, exact-name, keyboard, stale-selection and real PTY fixtures.
The complete gate log is `/private/tmp/mos-ranked-resume-check.log`.

All package Python source bytes match the tested wheel. Wheel SHA-256:
`1174ee354f7aedbcd2f2c209536fd6e054457ec15243b8261f90b27d852d2591`.

No unresolved blocking finding remains for §31.6. The implementation introduces no
new dependencies, storage schema, provider access or release activation. Existing
platform/live-provider/publication gates remain separate. No paid calls, native
credential inspection or real session catalogs were used.

# G4 isolated correction write and Git integration boundary

This eighth **offline** G4 slice consumes a previously validated, child-signed
correction proposal. It does not reuse the child-dispatch grant as write authority.
The creator signs a separate exact integration grant binding the correction
admission, complete dispatch receipt, repository/source revision, changed paths
and a bounded deadline. A private task/cycle claim is spent before any Git write.

## Integration contract

The broker replays candidate, correction, child-dispatch, authenticated custody,
known-control, binding and read-only Git evidence. It requires a clean original
checkout, unchanged creator-test bytes and a source tree safe for a bounded
checkout: at most 2,048 regular blobs and 32 MB, with no links, submodules,
attributes, Git-control paths, control characters or case/normalization aliases.
The existing Git `info/attributes` must be absent or empty. These restrictions
are deliberate for this initial offline boundary; unsupported repositories stop.

After those checks, the broker creates a detached worktree inside an existing
owner-private store **outside** the repository. Fixed Git arguments disable hooks,
global/system configuration, optional fsmonitor, sparse checkout and CRLF
conversion for the checkout/write path. Only existing proposal-owned regular
files are overwritten through no-follow file descriptors. The broker stages only
the signed changed paths and makes one local commit with a fixed identity; it
does not move the original branch, merge, push, delete, rewrite history, or run
tests. The resulting commit must be a direct child of the signed source revision.
The exact changed paths, worktree bytes, Git blobs, binary patch, tree ID, clean
worktree and unchanged original HEAD are checked after commit. Original source
provenance is replayed again. A separate enrolled VCS key may sign the canonical
integration record, which can be replayed against the complete upstream chain.

A failed, timed-out or interrupted attempt leaves its one-use claim and any
partial detached worktree for inspection. There is no automatic retry or cleanup.
The private store and same-UID host are trusted; this is not a hostile-host
sandbox. Checkout runs trusted Git over a pinned, restricted tree and is not a
general repository writer. No provider call or measured-spend claim is made.

## Remaining gates

The new commit is **not** a correction-cycle completion or accepted result.
Production coding-child broker authorization and measured spend, refreshed
binding/custody/Git/candidate evidence for the new revision, authenticated critic
quorum, final creator and reviewer whole-suite execution, and independent
implementation review remain separate. See the [roadmap](ROADMAP.md),
[threat model](G4_CORRECTION_INTEGRATION_THREAT_MODEL.md), and
[verification record](G4_CORRECTION_INTEGRATION_VERIFICATION.md).

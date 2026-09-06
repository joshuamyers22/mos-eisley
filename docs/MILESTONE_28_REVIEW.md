# Milestone 28 adversarial review: transactional skill quarantine staging

## Disposition implemented

Materialize exact latest-controlled candidate or rollback bytes only into an isolated
private quarantine store. Use completion-marker-last writes, full post-write semantic
reverification, durable atomic rename, bounded conservative crash inventory, and an
anchor lock spanning the commit. Grant no installation or runtime authority.

## Adversarial findings addressed

| Attack or ambiguity | Disposition | Remaining limit |
|---|---|---|
| A copied receipt stages substituted bytes | Reauthenticate the complete release lineage and reconstruct the selected archive from every post-write payload byte | Upstream trust-policy distribution remains external |
| An old allow races a new revocation | Hold a verified anchor read transaction across staging commit so a newer state cannot commit between check and rename | Owner-driven whole-database replacement still needs an external witness |
| A crash exposes partial content as complete | Write in a separate transaction directory, write the manifest last, verify, fsync, then atomically rename to the content digest | Incomplete transactions are reported but not automatically recovered or deleted |
| Directory entries disappear after power loss | Fsync files, every nested directory, both rename directories, store root, and store parent | Filesystem/hardware durability semantics and parent ownership remain trusted |
| Traversal, symlink, hard-link, or special-file content escapes quarantine | Revalidate bounded relative paths and exact inventory; require private regular single-link files and non-symlink private directories | Same-UID replacement of trusted ancestors is not contained |
| Existing content is silently overwritten | Content-addressed destinations are verified and reused only when they reconstruct the exact archive; no update-in-place path exists | Concurrent same-UID mutation can cause denial of service |
| Partial transactions exhaust disk or package counts grow unbounded | Policy caps completed packages and incomplete transaction directories; new writes fail at the bound | Cleanup is intentionally manual and operator-controlled |
| “Staged” is interpreted as “installed” | Every contract/event fixes install, activation, and configuration authority false; no runtime consumer or default pointer exists | A future installer needs an independent signed authorization design |

## Stop condition

This milestone stops at inert quarantine. It does not add a runtime search path,
default-persona mutation, install authorization, automatic rollback, or deletion.
The next slice should design a signed one-use install decision and atomic pointer
transaction with recovery and post-commit verification before any staged prompt can
influence a model request.

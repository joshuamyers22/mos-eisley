# Milestone 31 adversarial review: atomic skill default selection

## Disposition implemented

Use an authority independent of evaluation, promotion, release control, and installation
to sign one exact state transition. Consume that decision and change the private inert
default pointer in one SQLite commit while the latest release-control guard is held.

## Adversarial findings addressed

| Attack or ambiguity | Disposition | Remaining limit |
|---|---|---|
| Installation permission silently implies default selection | A distinct Ed25519 policy and domain authorize only one default-pointer transition | Organizational independence, policy delivery, and key custody remain external |
| A signer selects nearby or replaced bytes | Decision binds the exact installed manifest, historical installation authorization/decision, archive, persona, and installed-store policy | Package authorship and signer judgment remain trusted externally |
| Two valid decisions race or overwrite history | Signed next sequence and prior-pointer digest form compare-and-swap; one SQLite writer serializes the recheck and commit | Same-UID database replacement can deny or bypass without stronger OS isolation |
| A crash consumes authority without changing the pointer | Immutable revision insertion and singleton pointer update share one rollback-journal transaction | A caller that loses the commit response must inspect status before deciding what happened |
| A revocation lands during the change | Full lineage is reverified and the latest release-control read guard remains held through pointer commit | External revocation delivery and whole-anchor rollback remain outside the local lock |
| Default is confused with active runtime behavior | Results say `default_changed: true` while runtime lookup, activation, and all other configuration mutation remain false; no runtime reader exists | A later runtime-consumption layer needs separate authorization and drift gates |
| Local history is edited after selection | Every status read reverifies canonical signed records, exact installed packages, pointer hashes, sequence, and full chain | The owner can rewrite or roll back all local stores without an external monotonic witness |
| Revision history exhausts memory before validation | Store policy caps record count, aggregate bytes, and individual record bytes before rows are loaded | Database pages and installed-package verification still consume bounded local resources |

## Stop condition

This milestone stops at a private control-plane pointer. It does not inject a persona
into a request, activate runtime lookup, uninstall packages, measure post-selection
health, or monitor drift.

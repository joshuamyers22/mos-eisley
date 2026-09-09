# Milestone 89 adversarial review: calibration execution decision

## Disposition

Accept as an offline, independently signed prerequisite to one future paid
assignment. Do not treat the authenticated receipt as proof that one-use authority
has been consumed or that any request was sent.

## Findings and controls

- **A sequence number alone is ambiguous.** The decision fully reconstructs the
  manifest and binds sequence, batch position, sample, candidate, evaluation-request
  hash, model, effort, and profile-plan hash.
- **A signed assignment could still permit request mutation.** Derivation builds the
  existing strict `Critique` Responses request and signs its approved-request hash,
  including instructions, blinded brief, output cap, default tier, disabled storage,
  disabled streaming/background, disabled truncation, and no tools.
- **Campaign ceilings could diverge from enforceable pricing.** The decision rejects
  schema 1 and requires every schema-2 rate, token limit, source, model, tier, and
  worst-case reservation to exactly equal the selected campaign profile.
- **A valid decision could target a substituted, overbroad, blocked, or exhausted
  ledger.** Derivation and authentication bind the canonical ledger policy as well
  as its identity, reject aggregate ceilings above the campaign maximum, and require
  the ledger to be unblocked, sufficiently funded, and free of the deterministic
  audit-path entry.
- **Read-only authentication is not atomic consumption.** A concurrent change can
  occur after inspection. The future paid consumer must atomically reserve the exact
  ledger-entry ID before credential access; duplicate reservation is the one-use
  enforcement point. No automatic retry or release is authorized.
- **Path substitution could redirect evidence.** The resolved fresh audit-path digest
  is both signed and used as the future ledger-entry ID. Existing paths and output
  overlap are rejected.
- **A compromised or substituted signer could authorize spend.** The decision binds
  the exact authority-policy hash and verifies an enrolled Ed25519 public key over a
  domain-separated message. CLI commands never accept private signing keys.
- **Stale decisions or prices could survive source changes.** Both the authority and
  exact schema-2 spend policy bound the decision's maximum five-minute window;
  authentication rebuilds all sources and checks current time.
- **Offline commands might accidentally expose prompts through a provider.** Both
  commands reject supported credential variables before reading source files and
  contain no transport call. Outputs contain hashes and signed metadata, not briefs.

## Residual risks

The authority roster has no revocation anchor, signer separation from every prior
evaluation role is an operational policy rather than reconstructed proof, and local
trust roots can be replaced by an attacker controlling all source files. The route's
client version is source-bound, but installed SDK equality is deferred to the paid
preflight. Ledger inspection and authentication do not prevent a later competing
reservation; only the next atomic consumer can close that race. Provider usage,
billing, authorship, quality, and invoice finality remain unproven.

# G4 carry-forward final-suite verification

Objective: run one creator-signed pair of whole suites on integrated commit
`f54e815987c1e51941abf4c2f2138a7268dcf0a7` and verify the private receipt.

Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`,
`templates/THREAT_MODEL.md`, and `templates/WORK_NOTE.md`.

Invariants: no provider call, no repository write, no credential access by test
workers; exact signed authority and one-use claim; unchanged protected creator
bytes; exact integrated Git and reviewer identities; no acceptance claim.

The reusable creator package was verified against the historical signed
assignment and its original Git lineage. Its protected test blob SHA-256 is
`c270eb0390dcb83546ac1be3482409280850fbe22d427268a18e6e82634bceb5`,
which equals the integrated commit blob. The passing carry-forward candidate
receipt is `f85e0b7006c11f9da54b452c7a975301720ac3f5c6dbe15101e5119f9521d2c8`.

Threats addressed: stale or substituted Git tree, substituted frozen package,
disguised protected tests, changed execution requests, unauthorized signer,
claim replay, changed reviewer test selection, container/network escape.
Mitigations: full signed-chain replay, Git/blob comparison, original package
derivation checks, domain-separated Ed25519 verification, exclusive private
claim, worker image identity, and no-mount network-disabled execution.

Final outcome and receipt hash are recorded in the private owner-only run
folder after execution. This repository note contains no private key, provider
payload, or hidden test material.

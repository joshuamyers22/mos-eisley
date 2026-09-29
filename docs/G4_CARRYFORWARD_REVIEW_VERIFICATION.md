# G4 carry-forward review verification record

Objective: prepare a fresh two-provider, one-owner review of integrated commit
`f54e815987c1e51941abf4c2f2138a7268dcf0a7`, bound to final-suite receipt
`ce0eea46177b69f5e992dca1f9222f91d1a7da56bc7d250863b9e4afabf5fb15`.

Selected guides: `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`,
`templates/THREAT_MODEL.md`, and `templates/WORK_NOTE.md`.

Blocking risks: stale or substituted Git/plan/final receipt; an expired or
misbound signature; unauthorized provider transfer or spend; replayed one-use
claims; fabricated observation or judge lineage; unsupported citations; a
one-signer record presented as formal independent review.

Acceptance evidence: replay current signed integration, passing candidate and
final suites; compare the exact approved plan and full Git patch; verify one
owner-signed authority and exact provider call grants; retain and settle every
provider audit; validate critic citations and deterministic judge verdict; have
Joshua review and sign the final owner decision; replay the assembled record.

Stop on failed replay, source or receipt drift, missing signature, expired
window, invalid citation, unresolved ledger exposure, or spent claim. A failed
call is retained and never silently retried. Private provider payloads, signing
keys and raw reviewer text remain outside Git.

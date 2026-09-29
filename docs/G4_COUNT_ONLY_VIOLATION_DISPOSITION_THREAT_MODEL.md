# G4 count-only Anthropic violation disposition

## Scope

This change permits an exact, owner-signed release of the USD 0.104960 hold
for failed G4 Anthropic grant `g4-q3-evidence-anthropic-critic-live-1` on
integrated commit `d7237f5`. It does not authorize a new provider call,
formal independent review, or G4 acceptance.

Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`,
and `templates/THREAT_MODEL.md`. The private disposition script and signed
artifact stay outside Git.

## Evidence and trust boundary

The failed claim contains a signed grant, admission and authorization, a
`violation` spend receipt for the full hold, and a failed outcome with no
provider response. The pinned controller code records this violation after
Anthropic token counting exceeds the reserved input limit, before calling the
Messages endpoint. Anthropic's [token counting documentation](https://platform.claude.com/docs/en/build-with-claude/token-counting)
states that token counting is free. The script checks exact artifact and source
digests, the enrolled creator signature, the ledger entry, and absence of a
message response before presenting the zero-charge disposition to Joshua.

The Console invoice for this call was not checked. Local files cannot prove
that no unrelated or out-of-band message request occurred. The disposition
addresses this one audited controller attempt and published endpoint price.

## Controls and recovery

| Risk | Control |
|---|---|
| Release another entry | Exact ledger ID, entry ID, reservation digest, and prior full hold |
| Treat an arbitrary violation as free | Caller verifies pinned count-before-message code and exact failed claim; ledger method only accepts zero |
| Double release or conflicting authority | Atomic reconciliation row, exact idempotent replay, conflicting replay rejected |
| Erase the failure | Historical receipt and outcome remain unchanged; adjustment is separate |
| Reuse signature for another purpose | Domain-separated Ed25519 body names exact evidence, zero amount, and denied provider/G4 authority |

If billing evidence later contradicts the published free count policy or the
claim audit, preserve both records and open an incident for a separately
authorized correction. Do not silently rewrite the historical receipt.

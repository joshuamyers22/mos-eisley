# G4 production coding-child output incident

- Date, duration, severity, owner: 2026-09-26 22:41 Eastern; one call; qualification blocking; Joshua Myers.
- Impact: the authorized OpenAI coding-child request settled at $0.002675, but no valid child proposal or dispatch receipt was created. No host source write or G4 acceptance occurred.
- Detection: `_parse_model_proposal` rejected the provider's replacement before child signing. The one-use dispatch claim remains consumed. The shared ledger entry is settled, with no unresolved hold.

| Time (Eastern) | Evidence/event | Decision/action |
|---|---|---|
| 22:41 | Private response artifact SHA-256 `f831e74de6e060c1f510f72885f6e2caf843793476e908813ce566bbbe2e0083`; no response text in Git | Preserve audit privately. |
| 22:41 | Replacement encoded the intended one-line correction but omitted base64 padding and supplied a placeholder digest | Reject under the current strict source-file contract; do not retry the spent claim. |
| 22:42 | Ledger entry `b5fc52fba5d7b5f99a9a35e9833de0dfe62c4ded2c0bf593af9799296b65d393` settled at 2,675 micro-USD | Keep the charge and the failed attempt in the record. |

The provider cannot reliably compute a cryptographic digest. The child broker now decodes a bounded, unambiguous base64 value, computes the digest over the decoded bytes, and then constructs the strict source-file contract. The untrusted response remains intact in the private audit, and the enrolled child still signs only the validated proposal. Invalid base64, unsafe paths, duplicate JSON keys, unauthorized files, and empty changes remain rejected by the existing boundaries.

This correction changes the broker's trust boundary. It requires accountable review and a new exact one-use provider grant. The failed attempt's claim and grant must never be reused. A subsequent valid proposal will be a separate run, not a retroactive repair of this incident.

## Second one-use attempt

At 23:17 Eastern, a separately signed recovery request used the normalized source-file parser. The provider returned malformed JSON with a stray quoted key near the end of an otherwise bounded response. The broker rejected it before child signing. Its distinct one-use claim remains spent and ledger entry `d5b29033b97213a447c940fbab671e0f606a2ba206145b5a867f2cec6c59f39e` settled at 2,465 micro-USD; no host write or dispatch receipt exists. The next request adds the project's supported strict JSON Schema output format. This changes the exact provider request body and requires a new signed grant and claim.

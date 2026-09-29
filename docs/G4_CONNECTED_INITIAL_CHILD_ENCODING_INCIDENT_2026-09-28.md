# Incident review: connected initial-child source encoding

- Date: 2026-09-28 UTC
- Severity: bounded qualification attempt failed after a paid provider response
- Owner: Joshua Myers
- Impact: one exact OpenAI call settled at 3,238 micro-USD; no child proposal,
  source integration, test result, or G4 acceptance was created

| Time (UTC) | Evidence/event | Decision/action |
|---|---|---|
| 2026-09-28 02:17–02:18 | One-use grant `6b8ca0864ce5…` reached OpenAI; private response hash `2117e7896cfb…` and spend receipt were retained. | Grant and initial dispatch claim remain spent. |
| 2026-09-28 02:18 | The structured response had one replacement with one ASCII space inside an otherwise canonical base64 field. The broker rejected it before child signing. | No response text was copied into Git; no source write occurred. |
| 2026-09-28 | Private ledger entry settled at 3,238 micro-USD. | No uncertain hold to reconcile. |

## Trigger and controls

The strict decoder admitted canonical padded or unpadded base64 only. Removing
the single space yields one valid canonical decoding, but the original response
was correctly denied by the then-current broker. The strict JSON schema did
not constrain the internal base64 alphabet. The outer audit, response hash,
one-use claim and settled ledger preserved the failed attempt.

The corrective change allows at most 16 ASCII spaces inside a base64 field,
then requires valid alphabet, strict decoding and canonical re-encoding before
signing decoded bytes. It continues to reject other whitespace, invalid
characters and ambiguous encodings. The raw provider response remains in the
private audit. Focused parser tests cover the accepted spacing and rejection
cases. A new initial-child attempt needs a fresh assignment, dispatch and exact
live grant; this call cannot be retried or counted as a connected path.

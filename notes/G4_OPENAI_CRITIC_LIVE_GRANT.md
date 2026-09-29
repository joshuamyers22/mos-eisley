# G4 OpenAI critic live grant

- Owner: Joshua Myers. Risk: high because the call crosses credential, network,
  authorization, and spending boundaries.
- Subject: the frozen G4 review subject and signed single-operator roster.
  The request must match the roster's `openai-critic` hash and persona.
- Route: one `gpt-5.6-luna` Responses token count and one standard-tier
  structured-output Responses call at low reasoning effort. No tools,
  provider storage, truncation, redirect, or automatic retry is authorized.
- Pricing: the [official model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
  lists USD 0.20 input, USD 0.25 cache-write, and USD 1.20 output per million
  tokens for standard processing. A 64,000 input and 4,096 output token
  envelope holds 20,916 micro-USD. The shared G4 ledger caps all review
  calls at 10,000,000 micro-USD.
- Authority: the enrolled creator signs a separate one-use exact request and
  spend grant. The claim is burned before token counting, and the full hold
  remains if spending is uncertain. The grant cannot establish independent
  review or acceptance.
- Evidence: focused grant, signature, lineage, expiry, and one-use dispatch
  tests plus the project full quality gate. Credentialed operation remains a
  separate step after signing.

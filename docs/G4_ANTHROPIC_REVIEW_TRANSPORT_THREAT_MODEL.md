# G4 Anthropic review transport threat model

## Scope and ownership

Owner: Joshua Myers. Scope: one Anthropic critic call for the frozen G4 review
subject, its signed owner authority, API credential, private audit and shared
spending ledger. The judge, OpenAI critic and formal independent-review gate are
outside this slice.

## Assets and boundaries

| Asset | Boundary and control |
|---|---|
| API key | Local hidden prompt; HTTP header only; no persistent artifact |
| G4 subject and critic request | Exact hashes in owner authority and call grant |
| Provider body | Exact hash in grant; fixed HTTPS endpoints and output schema |
| USD 10 allowance | Shared durable ledger; conservative pre-reservation |
| Provider response | Private bounded audit; parsed citation evidence |

## Abuse cases and controls

| Case | Control and evidence | Residual risk |
|---|---|---|
| Unauthorized transfer or replay | Two domain-separated creator signatures, exact body hash, O_EXCL one-use claim | Compromised creator key |
| Prompt injection | Quoted source treated as data; output evidence checked against exact catalog | Model can still produce poor analysis |
| Endpoint/response abuse | Fixed URLs, no redirects/retries/tools, bounded bytes and timeout | Provider or local TLS compromise |
| Spending overrun | Upper cache-write reservation, response usage/tier checks, durable ledger | Provider billing may differ from API usage; uncertain charge stays held |
| Cancellation or process death | Claim and hold precede network; uncertainty conservatively retained | Manual reconciliation may be needed |
| Key or subject disclosure | Key never persisted; exact reviewed subject is sent only after grant | Provider receives the approved subject |

The single human signer authenticates owner intent and self-review risk, not
provider operation or independent human review. The signed call grant cannot
authorize G4 acceptance.

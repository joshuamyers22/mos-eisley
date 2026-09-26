# G4 Anthropic review transport and live grant

- Owner: Joshua Myers. Risk: high, because this crosses credential, data-transfer,
  authorization and spending boundaries.
- Objective: qualify one fixed Sonnet 5 critic route for the frozen G4 subject and
  prepare a separately signed, one-use transfer and spending grant.
- Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`,
  `docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`,
  `templates/THREAT_MODEL.md`, and `templates/WORK_NOTE.md`.
- Authority: one creator signs the single-operator review roster and, separately,
  the exact Anthropic call. The separate call grant explicitly authorizes only
  its credential access, network transfer and provider dispatch. Both preserve
  `independent_review_evidence_passed=false` and `acceptance_authorized=false`.
- Fixed route: Anthropic Messages and token-count endpoints, `claude-sonnet-5`,
  JSON schema text output, standard-only service tier, global inference, no
  tools, redirects or retries. A local key prompt is required only in the
  private runner; the key is never part of grant artifacts.
- Cost envelope: 16,000 input tokens and 4,096 output tokens, with every input
  token reserved at the upper cache-write rate. At the current Sonnet 5 public
  rates this is 104,960 micro-USD per critic call. The shared G4 ledger ceiling
  is 10,000,000 micro-USD, matching the owner's USD 10 cap.
- Failure rule: burn the signed claim before a request; reserve first; retain the
  full hold if token counting, generation, parsing or cancellation leaves spend
  uncertain. A pricing violation blocks the ledger. No automatic retry.
- Scope limit: owner-reported Models API HTTP 200 establishes availability.
  Credentialed Messages conformance and the actual critic result require the
  signed live grant; offline tests alone do not prove provider operation.
- Acceptance evidence: focused HTTP/ledger/signature/replay tests, type/lint,
  and `make check`. The owner must inspect and sign exact canonical payloads
  before a live call. The formal independent-review gate remains open.
- Verification: 2,534 source tests and 1,888 installed-wheel tests passed; see
  `docs/G4_ANTHROPIC_REVIEW_TRANSPORT_VERIFICATION.md`. The shared ledger has
  zero entries and no grant has been signed as of this preparation record.

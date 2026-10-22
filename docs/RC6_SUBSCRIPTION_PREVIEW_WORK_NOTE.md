# Subscription live journeys and rc.6 preview

- Owner: Joshua Myers
- Status: active
- Started: 2026-10-22 UTC
- Baseline: main `77dfa8b5b3aa8ddabc503dc0d9546b3c9bd3527e`
- Branch: `feat/subscription-preview-rc6`

The owner requested actual ChatGPT and Claude subscription conversations, quit and
cold resume with retained limits, correction of plain-mode provider labels, and
inclusion in the next signed installable preview. The current published preview
is rc.5; prepare rc.6 without rewriting any prior release or tag.

Selected guidance: `AGENTS.md`, `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`,
`templates/THREAT_MODEL.md`, `templates/WORK_NOTE.md`,
`docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`, and `checklists/RELEASE_READINESS.md`.

Invariants: native clients retain credentials; exact admitted versions/profiles,
tool denial, explicit transfer/quota/native-retry acknowledgement, immutable
authorization, expiry and ledger, no API fallback and no automatic replay remain
unchanged. Preserve existing owner configuration, sessions and installed rollback.
Use only synthetic messages and empty disposable workspaces for live checks.

Live ceiling: at most four Mos inference invocations total, two per provider,
using one fresh two-invocation scope for each route. The second exchange follows
quit/cold resume and checks recall of a harmless marker from the first exchange.
Verify scope bytes and usage before/after resume, then attempt a third exchange
and require local allowance refusal without another native invocation. Native
retries and provider billing remain unverified and are not bounded by Mos call
counts. Stop that provider on failure, cancellation, uncertain usage, unexpected
tools, changed identity or exhausted allowance. Do not replace failed scopes or
send additional probes without a new owner decision.

Preflight observed an owner-installed Codex update to 0.163.0. The existing exact
allowlist refused before authentication/inference; Claude 2.1.283 remains ready.
Qualify 0.163.0 through the existing loopback fixture before adding exact version
admission for the current shortcuts. Retain 0.161.0/0.162.1 and unknown-version
refusal; do not relax native tool/config controls. No live scope has been used.

Threat review: use existing checked private state and executable/context binding;
no credential-cache inspection, copied secrets, repository tool grants or project
data transfer. Retain private operational receipts outside Git. Track concise
results only, never transcripts or raw provider payloads. Sampling stores and
artifacts are outside scope. This agent's review is not independent approval.

Acceptance: both actual routes complete the bounded start/resume journeys and
retain limits; provider-aware plain welcome text distinguishes subscription
authorization from API spending policy; focused presentation and subscription
checks pass; one combined candidate `make check audit` passes; rc.6 source, tag,
artifacts and enrolled signatures agree; native signed install and published
predecessor upgrade gates pass. Prepare concrete release evidence before any
protected publication approval. Apple signing/notarization and cask publication
remain separate. Keep GitHub environment protections intact.

Budget: one implementation slice, focused checks, one combined full gate, and
one qualified release candidate. Additional checks must address changed evidence
or a concrete failure. Stop publication on failed checks, identity/state loss,
missing approval or unresolved live-route failure; retain all failure receipts.

## Initial acceptance evidence

- All 82 focused subscription checks passed, including real plain launcher and
  cold-resume provider labels, all admitted Codex dispatch versions and unknown
  version rejection before authentication.
- Actual Codex 0.163.0 passed the loopback-only fixture with fake authentication,
  exact model/effort and an empty tool inventory. Native sign-in preflight then
  admitted both existing accounts without credential-cache inspection.
- Live ChatGPT (`gpt-6-sol` / `medium`) and Claude (`claude-sonnet-5` / `high`)
  each completed an initial synthetic exchange, quit/cold resume and a contextual
  follow-up. Each original two-invocation grant stayed byte-identical even when
  resume requested a larger limit. A third exchange failed locally with exactly
  two dispatch receipts and two completed ledger slots. Four native inference
  invocations total; no extra probes or recovery scopes. Billing remains unverified.
- The first live harness counted both native completion receipts and ledger
  completion receipts, failing its final count assertion after ChatGPT's two
  exchanges and local ceiling refusal had completed. Corrected the counter and
  independently closed the existing ChatGPT evidence offline, with no replay.
  ChatGPT's initial quit/terminal restoration passed; its resumed terminal cleanup
  was interrupted by that harness assertion, so no resumed restoration claim.
  Claude passed the corrected journey and both terminal restoration checks.
- Private operational evidence is retained outside Git under
  `~/Projects/mos-eisley-rc6-validation`; no transcript or provider payload is
  included here. The full candidate gate, exact-head delivery CI and signed
  rc.6 qualification remain pending.
- Pin immutable published rc.5 release `420137559` / source `b049065` as an
  additional predecessor on all four native release targets. Retain the existing
  rc.1/rc.2/rc.3 upgrade gates, enrolled-signature checks and protected publication.

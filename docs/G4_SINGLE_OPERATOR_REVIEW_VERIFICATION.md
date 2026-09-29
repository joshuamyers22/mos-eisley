# G4 single-operator review preparation verification

- Starting branch: `docs/g4-qualification-preparation` at `1b1fba9`; work branch:
  `feat/g4-single-operator-review`.
- Requirement: owner instruction for two model provider families (OpenAI and
  Anthropic) with one human signer, tied to the exact G4 subject. The existing
  independent-signer gate remains unchanged.
- Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`,
  `docs/AGENTIC_VERIFICATION_GUIDE.md`,
  `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`, and
  `templates/WORK_NOTE.md` from the template revision pinned by `AGENTS.md`.
- Risk: high. No live spend or credential use is part of this implementation.

## Blocking rubric

| Dimension | Required evidence |
|---|---|
| Exact subject | Recompute plan, full Git diff and final suites before assembly and verification. |
| One human signer | Authority and final decision verify against the same enrolled creator key under separate domains; policy must be single-operator. |
| Two model families | Completed critic quorum must cover two distinct declared providers; each request hash and citation catalog is reconstructed. |
| Judge lineage | Derived, bounded request and all critic/judge observation hashes match the owner's signed decision. |
| Honest status | No independent signer, provider operation or acceptance proof can be set true. No provider or private-key capability exists in the CLI. |

## Current offline evidence

Five focused tests pass: accepting owner-attested record with all independence
flags false, changed observation rejection, foreign owner-key rejection,
missing two-family quorum rejection, and end-to-end CLI assembly/replay with
private file mode. Ruff and project Pyright pass. The independent-review tests
remain separate and unchanged. The permissioned `make check` ran all 2,519
source tests (four skips) but failed with three errors and one failure in
pre-existing OAuth, candidate-execution, and skill-installation tests. Each
of those three named tests passed in isolation; the OAuth rerun required
localhost socket permission. The cause was the invocation's `umask 077`:
the latter tests create intentionally public fixture directories and require
their requested `0755` bits to remain; the restrictive umask changed them to
`0700`. The normal-umask rerun passed all 2,519 source tests with four skips and
88% total coverage. Export verification and wheel build passed separately.
Installed-wheel smoke initially passed 1,868 tests. Its explicit test list then
gained the new single-operator review test; the affected smoke rerun passed
1,873 tests. No live conformance or actual model result is claimed.

## Remaining boundaries

Implement and qualify an Anthropic critic transport under exact transfer,
isolation, cancellation, one-use and shared spending controls; select available
model IDs and current pricing; obtain a separate live-call grant; retain
provider responses/audits; obtain the owner's separate signed review authority
and final decision. Even then, the formal independent-review gate remains open
until its distinct external signer roster is available.

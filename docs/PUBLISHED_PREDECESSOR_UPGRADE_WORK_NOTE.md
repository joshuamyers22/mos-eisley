# Published predecessor upgrade qualification

- Status: prepared; exact results and accountable disposition are maintained in [delivery PR #305](https://github.com/joshuamyers22/mos-eisley/pull/305).
- Owner: Joshua Myers
- Started: 2026-10-14 UTC; refreshed for concurrent SDK updates on 2026-10-15 UTC.
- Frozen main baseline: `ab6024899d31cbf7f7463993e789838690dbac30`.
- Signed preparation head: `c090592ccc08b8bee118e9ae40e93875b17c1e0f`.
- Actual native checkout: `8ef4e6210dae6f455ac3dd7bc82097fd210aeb9e`.
- Both preparation/native checkouts have tree `b7857149eed6ca359eefac7ba363cb735207217f`.
- Predecessor: immutable published `0.1.0-rc.1`, source `8cf38c83591e505a9c7b57f4d701b12cb80fc4c6`.
- Candidate: unpublished `0.1.0-rc.2`, Anthropic 1.13.0 and OpenAI 3.26.0 from the reconciled lock.
- Review at delivery acceptance; do not reuse this qualification for changed artifacts.

## Objective and authority

The owner requested upgrades from the actual published predecessor, preserving
sessions through recovery, rollback and uninstall. This task prepares and qualifies
an unpublished candidate; it authorizes no version tag, application release, npm
publication, tap update, paid provider call or study. WSL2 remains postponed.
All original user worktrees and stored sessions are preserved.

Selected guidance: `AGENTS.md`, `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/WORK_NOTE.md`,
`templates/AGENTIC_VERIFICATION_LOOP.md` and `templates/THREAT_MODEL.md`.

## Blocking acceptance rubric

| Dimension | Required evidence |
|---|---|
| Real predecessor | Untouched public archive, enrolled-key signed metadata and native bootstrap; immutable release/source identity and checksum checks. |
| Candidate | Passing four-platform native build, actual checkout identity, enrolled-key signed inventory, exact version/archive/bootstrap hashes. |
| Session compatibility | rc.1 creates JSON and SQLite recorded sessions; both versions cold-resume them; rc.1 reads state explicitly advanced by rc.2 after rollback. |
| State integrity | Session file hashes and inert credential/config/spending sentinels stay unchanged around lifecycle operations; only explicit recorded turns may change sessions. |
| Recovery/refusal | Interrupt immediately before and after durable activation, recover the expected committed version and clear the transaction. Refuse altered archives and runtimes. |
| Native behavior | Both frozen installers/runtimes run on macOS/Linux arm64/x86_64 without Python or Node on PATH; actual frozen recovery/rollback/uninstall commands execute. |
| Delivery | Focused checks, one combined gate per changed SDK snapshot, final CI, retained four-platform evidence and accountable owner acceptance. |

## Trust boundaries and stopping rules

Both versions use the existing enrolled publisher root without a signature bypass.
The existing owner-operated signer reads the external private key directly. No
private key, encoded key, real provider credential or user payload enters Git,
logs or retained artifacts. The committed candidate inventory contains public
signatures/hashes only and is preparation evidence, not publication permission.

Journeys use fresh private temporary roots, inert recorded conversation fixtures
and synthetic credential/config/spending sentinels. Real user data and sampling or
evaluation stores remain outside scope. Fault injection changes only the source
installer's activation interruption point; signature/archive/runtime verification
remains intact. Actual frozen CLI commands recover and roll back without patches.

Budget: three initial passes, one bounded installed-wheel fixture correction and
one refresh after concurrent main SDK/action updates; one combined local gate per
SDK snapshot, affected checks after later changes, and final CI. No provider spend.
Stop on signature/source/platform/version mismatch, data loss, failed resume or a
publication mismatch. A later changed candidate needs fresh qualification.

## Implementation and artifact provenance

[Native build 38664890848](https://github.com/joshuamyers22/mos-eisley/actions/runs/38664890848)
binds the preparation and actual checkout identities above. Every downloaded
archive/bootstrap is checked against its native qualification record before the
owner-operated signer produces [candidate metadata](qualification/rc2-upgrade-candidate.json).
The untouched predecessor metadata and platform archive are checked with the
enrolled public root, and its bootstrap matches published `BOOTSTRAP_SHA256SUMS`.

`tools/qualify_published_upgrade.py` performs actual installation, recorded session
creation and cold resume on both backends, upgrade, candidate writes, rollback,
both interruption/recovery paths, tamper refusal, uninstall and predecessor
reinstallation/resume. It emits compact identities/outcomes without session
contents. `published-upgrade.yml` downloads the pinned candidate and immutable
predecessor on all four actual platforms and retains those results.

The protected tagged release workflow also requires this real-predecessor journey
against the exact newly signed tag artifacts before publishing. Its source argument
is the tag checkout SHA, not the preparation fixture's source. New results join
the retained signed qualification inventory. This prevents an eventual tagged
rebuild from inheriting preparation evidence for different bytes. Existing owner
environment approval, draft-first publication, signing and npm controls remain.
The signed qualification job has a bounded 30-minute timeout for the added journey.
No tagged release is executed as part of this task.

## Observations and corrections

The first candidate snapshot used the older SDK lock. It passed the actual local
journey and all four native lifecycle steps. Its first matrix failed evidence
upload because the uploader excluded hidden `.work` paths. The correction writes
only compact results under `dist/qualification`; the corrected matrix retained
all four records and their signed identities were verified.

Installed-wheel inspection found the new helper missing from the copied test
fixtures. The correction copies both helpers outside site-packages; no tests are
excluded. All 37 distribution checks passed against a fresh installed wheel
outside the checkout. That SDK snapshot's full gate passed 3,719 source tests
(17 skips), 85% coverage and 2,728 installed-wheel tests (13 skips).

Main then advanced through already merged SDK/action updates. The branch was
reconciled through GitHub's normal update API, preserving those changes. The
older candidate evidence remains attributed but is superseded for current
acceptance. The refreshed native build, signature inventory, actual journeys and
combined SDK gate are required separately; final identities/results are recorded
in PR #305. Focused publication checks also enforce that tagged publication cannot
skip the actual-predecessor journey or substitute a preparation source SHA.

## Limits and handoff

This is exact-pair standalone evidence, not general task reliability or stable v1
acceptance. No project storage schema changed; the SDK refresh is included in the
candidate artifacts. Future runtime/dependency/schema changes need fresh evidence;
package-manager upgrades, WSL2, billing/native retries/general reliability and
independent encrypted publisher backup/restore remain separate work.

GitHub native build-artifact retention bounds future fixture replay. A changed
preparation candidate needs a fresh passing native run, verified checkout tree
and signed inventory. The tagged publication gate instead uses that tag's own
freshly signed artifacts. rc.1 remains immutable, and rc.2 remains unpublished.

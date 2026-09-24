# Adversarial Code and Architecture Review: G4 bounded correction gate

## Review metadata

- Repository: Mos Eisley; branch `feat/production-template-guidance`.
- Revision: working tree after `62bdcd1`; review date 2026-09-24.
- Reviewer: Codex self-review; **not** independent approval.
- Purpose: bind one failed reviewer-test finding to a bounded, non-dispatching
  correction evidence transition.
- Runtime/scope: Python 3.12; correction controller/CLI, worker observation,
  candidate/provenance links and focused fixtures. Generated/provider output is
  excluded.
- Starting worktree: clean.
- North star/rubric: plan L2/L3 and correction verification record; any unsigned,
  unreproduced, stale or unbounded repair is blocking.
- Ceiling: implementation and two evidence-changing passes; stop on a failed
  boundary or missing accountable review.

## Verdict

Offline evidence-controller design is suitable for further verification, **not
production release**. Its strongest property is exact replay of two candidate
receipts and a private two-cycle chain. Its highest residual risk is treating a
signed semantic disposition or critic hash as proof of genuine independent
review; this implementation does not make that claim.

## Verification evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Formatting/lint/type | `make check`; affected reruns | pass | source suite later stopped on sandbox loopback |
| Focused tests | `python -m unittest discover -s tests -p test_reviewer_correction.py -q` | 4 pass | real Git, worker, CLI, duplicate/forged/second-cycle paths |
| Build/smoke | `make verify-export build`; `make smoke` | pass | first smoke blocked by sandbox DNS; permitted retry ran 1,832 installed-wheel tests successfully |
| Architecture contracts | source trace | pass for offline scope | no child/provider/write/acceptance path exposed |

## Architecture map and challenge

CLI loads canonical private artifacts; pure contracts bind decision and budget;
controller verifies current candidate receipts and Git, claims a private store,
then later verifies a renewed provenance and candidate chain. It depends on the
existing candidate admission, isolated runner and read-only Git broker. The
product path never invokes child/model/provider code or writes the repository.

The critical state change is the exclusive task/cycle claim. A crash after the
claim cannot be retried as if nothing happened. A completion is also exclusive;
cycle two must replay exact stored bytes. Switching stores or same-UID tampering
is not prevented by content hashes alone and is an explicit trust assumption.

## Findings and improvement plan

| Severity | Finding | Evidence/consequence | Correction/acceptance |
|---|---|---|---|
| High, closed | count-only failure evidence | no exact test identity for triage | schema-2 IDs; two-run matching regression |
| High, closed | unpersisted predecessor | forged cycle history could consume cycle two | stored completion replay and tamper test |
| High, closed | per-cycle-only ceiling | repeated grants could exceed total allowance | fixed signed deadline/ceiling and carried reservations |
| High, open for production | critic quorum and citation semantics | a digest and signed judge assertion do not prove review quality | authenticate source review artifacts and obtain accountable approval |
| High, open for production | no correction execution containment | this gate deliberately grants no child dispatch | separate reviewed child/VCS/write adapter before production use |
| High, open for production | creator-test blob identity | approval hash is not a Git comparison of creator test files across revisions | bind exact creator-test blobs or require final whole-suite tree proof |
| High, closed for this artifact | full installed-wheel smoke | preceding aggregate smoke was non-green | fresh locked wheel ran 1,832 tests successfully |

No design claim here treats a model self-review as independent or a passing
candidate test as final acceptance. Next review should trace an actual bounded
child dispatch and final whole-suite/critic/judge workflow against these denials.

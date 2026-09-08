# OpenAI live-conformance exit gate

This gate defines the minimum evidence required before Mos Eisley may convert
brokered OpenAI conformance output into empirical calibration input. It is an exit
criterion, not execution authority. Every provider request still requires the exact
short-lived ceremony, independent signature, shared-ledger admission, and explicit
local data-transfer consent documented in
[OpenAI conformance](OPENAI_CONFORMANCE.md).

## Successful-profile matrix

The gate covers these exact profiles:

| Profile | Required consecutive authenticated successes |
| --- | ---: |
| `gpt-5.6-luna` / `low` | 3 |
| `gpt-5.6-terra` / `medium` | 3 |
| `gpt-5.6-sol` / `medium` | 3 |
| `gpt-5.6-sol` / `high` | 3 |
| `gpt-6-astra` / `high` | 3 |
| `gpt-6-astra` / `max` | 3 |

All 18 assignments must use distinct blinded sample IDs, be committed before their
outcomes are known, and complete through the exact zero-retry broker path. Each
success must have a response-received audit, settled and unblocked shared-ledger
entry, strict structured output, container-removal evidence, enrolled observer
signature, and freshly authenticated one-assignment conformance receipt. Model,
effort, request, SDK, pricing, token limits, batch, plan, ledger, and audit identities
must remain exact.

Every attempt counts. Attempted sample IDs and terminal dispositions must form a
complete chronological commitment; an unsuccessful attempt cannot be omitted or
replaced inside its tranche. After any unsuccessful attempt for a profile, that
profile requires three newly precommitted consecutive successes following a reviewed
root-cause disposition and regression test. No held, uncertain, violating, corrupt,
or unexplained entry may remain in a success ledger when the gate is evaluated.

The first authenticated Luna/low, Terra/medium, Sol/medium, Sol/high, Astra/high, and
Astra/max probes each count as one success. The first nine completed attempts from
the second campaign complete Luna/low, Terra/medium, Sol/medium, and Sol/high and
advance Astra/high to 2 of 3. Current progress is therefore 15 of 18: those four
profiles are complete at 3 of 3, Astra/high is 2 of 3, and Astra/max is 1 of 3. The
retained campaign receipts are documented in
[Milestone 55](MILESTONE_55_REVIEW.md),
[Milestone 56](MILESTONE_56_REVIEW.md),
[Milestone 57](MILESTONE_57_REVIEW.md),
[Milestone 58](MILESTONE_58_REVIEW.md), and
[Milestone 59](MILESTONE_59_REVIEW.md). The initial sealed campaign is complete;
the second campaign commits the 12 remaining attempts before their outcomes are
known, as documented in [Milestone 60](MILESTONE_60_REVIEW.md), and its first nine
authenticated results are documented in [Milestone 61](MILESTONE_61_REVIEW.md),
[Milestone 62](MILESTONE_62_REVIEW.md),
[Milestone 63](MILESTONE_63_REVIEW.md),
[Milestone 64](MILESTONE_64_REVIEW.md),
[Milestone 65](MILESTONE_65_REVIEW.md),
[Milestone 66](MILESTONE_66_REVIEW.md),
[Milestone 67](MILESTONE_67_REVIEW.md),
[Milestone 68](MILESTONE_68_REVIEW.md), and
[Milestone 69](MILESTONE_69_REVIEW.md).

## Failure-boundary suite

The success matrix is necessary but not sufficient. The following five distinct
boundaries must each pass once using the installed wheel and retained artifacts:

| ID | Boundary | Required evidence |
| --- | --- | --- |
| F1 | Pre-credential authorization rejection | An expired or exact-binding-mismatched signed authorization fails before API-key access, audit creation, Docker start, ledger admission, or provider request |
| F2 | Live provider authentication rejection | A separately consented exact request with a deliberately invalid credential records terminal `token_count` / `authentication_error`, creates no successful artifact or reservation, and permits no retry |
| F3 | Ambiguous post-reservation timeout or disconnect | A controlled fault after admission retains held or uncertain exposure in a dedicated ledger, writes a terminal classified audit, publishes no conformance artifact, and permits no retry or release |
| F4 | Invalid or identity-mismatched structured response | A controlled fault response is rejected before conformance publication, preserves conservative ledger state, and permits no retry |
| F5 | Launcher death after admission | A real-container fault proves exact-container watchdog removal and a read-only recovery result with no success or retry claim |

F1, F3, F4, and F5 are controlled operational tests and do not claim OpenAI behavior.
F2 contacts the real authentication boundary but does not prove that OpenAI inspected
or rejected any particular body. All five remain non-scoreable.

Deliberately ambiguous F3/F4 executions must use separately committed disposable
failure ledgers. Those ledgers are never reset, released, or reused for successful
probes. An unexpected violation in any live success run stops the whole OpenAI gate
pending a reviewed disposition and a new commitment.

## Gate output

The eventual gate report must reverify all 18 success lineages and the five failure
artifacts from their authoritative sources. It must report exact attempt coverage and
fix provider authorship, billing reconciliation, quality, calibration conversion,
promotion, and routing activation to false. A separate reviewed converter may be
designed only after this report passes; routing remains disabled until the later
calibration and holdout gates pass.

Changing the profile set, consecutive-success count, failure suite, or budget rules
requires a new public adversarial disposition before additional results are observed.

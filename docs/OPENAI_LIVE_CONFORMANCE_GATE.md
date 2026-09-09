# OpenAI live-conformance exit gate

**Status, 2026-09-09:** passed. The reviewed aggregate report is recorded in
[Milestone 85](MILESTONE_85_REVIEW.md). This status authorizes no provider request,
calibration conversion, scoring, promotion, or routing activation.

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
Astra/max probes each counted as one success. The first nine completed attempts from
the second campaign completed Luna/low, Terra/medium, Sol/medium, and Sol/high and
advanced Astra/high to 2 of 3. Its tenth attempt received and settled a provider
response but failed strict local validation after consuming the exact 512-token
output cap. The campaign is halted, and the Astra/high consecutive-success streak is
reset. Fifteen authenticated successes remain historical evidence, but current gate
credit is 13 of 18: those four profiles are complete at 3 of 3, Astra/high is 0 of 3
for its required replacement streak, and Astra/max is 1 of 3. The retained campaign
receipts are documented in
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
[Milestone 69](MILESTONE_69_REVIEW.md). The terminal tenth-attempt disposition,
failure-artifact recovery, and prohibition on running sequences 11 and 12 are
documented in [Milestone 70](MILESTONE_70_REVIEW.md).

A third, five-attempt recovery campaign is privately sealed and publicly committed
in [Milestone 71](MILESTONE_71_REVIEW.md). It assigns three fresh Astra/high attempts
to a replacement streak and two fresh Astra/max attempts to its remaining positions,
all under a new ledger and larger but bounded output and timeout limits. The
commitment authorizes no execution and does not change the current 13-of-18 gate
credit.

The first sequence-1 invocation stopped before broker admission because its locally
pinned image was absent. It sent no request and created no ledger entry, so sequence
1 remains unconsumed. The preserved stub, corrected immutable image binding, and
fresh-preparation requirement are documented in
[Milestone 72](MILESTONE_72_REVIEW.md). Gate credit remains 13 of 18.

The first admitted v3 execution subsequently completed and authenticated under the
corrected boundary. It is position one of the new Astra/high streak, advancing
current gate credit to 14 of 18 without authorizing sequence 2. Its exact evidence
and remaining denials are documented in
[Milestone 73](MILESTONE_73_REVIEW.md).

The second admitted v3 execution also completed and authenticated with a distinct
sample, request, ledger entry, response, artifact, signature, and receipt. It is
position two of the replacement Astra/high streak, advancing current gate credit to
15 of 18 without completing the profile or authorizing sequence 3. Its exact
evidence and remaining denials are documented in
[Milestone 74](MILESTONE_74_REVIEW.md).

The third admitted v3 execution completed and authenticated through another
distinct lineage. It completes the new three-success Astra/high streak and advances
current gate credit to 16 of 18 without completing the overall gate or authorizing
the Astra/max transition. Its exact evidence and remaining denials are documented
in [Milestone 75](MILESTONE_75_REVIEW.md).

The fourth admitted v3 execution completed and authenticated as position two of the
Astra/max profile. It advances current gate credit to 17 of 18 without completing
that profile, the overall gate, or authorizing sequence 5. Its exact evidence and
remaining denials are documented in
[Milestone 76](MILESTONE_76_REVIEW.md).

The fifth admitted v3 execution completed and authenticated through a distinct
lineage. It completes Astra/max, the five-attempt replacement campaign, and all 18
registered success positions. It does not complete the overall exit gate because
F1 through F5 remain outstanding, and it authorizes no additional provider request
or calibration conversion. Its exact evidence and remaining denials are documented
in [Milestone 77](MILESTONE_77_REVIEW.md).

## Failure-boundary suite

The success matrix is necessary but not sufficient. The following five distinct
boundaries must each pass once using the installed wheel and retained artifacts:

| ID | Boundary | Required evidence | Status |
| --- | --- | --- | --- |
| F1 | Pre-credential authorization rejection | An expired or exact-binding-mismatched signed authorization fails before API-key access, audit creation, Docker start, ledger admission, or provider request | Passed 2026-09-09 |
| F2 | Live provider authentication rejection | A separately consented exact request with a deliberately invalid credential records terminal `token_count` / `authentication_error`, creates no successful artifact or reservation, and permits no retry | Passed 2026-09-09 |
| F3 | Ambiguous post-reservation timeout or disconnect | A controlled fault after admission retains held or uncertain exposure in a dedicated ledger, writes a terminal classified audit, publishes no conformance artifact, and permits no retry or release | Passed 2026-09-09 |
| F4 | Invalid or identity-mismatched structured response | A controlled fault response is rejected before conformance publication, preserves conservative ledger state, and permits no retry | Passed 2026-09-09 |
| F5 | Launcher death after admission | A real-container fault proves exact-container watchdog removal and a read-only recovery result with no success or retry claim | Passed 2026-09-09 |

F1, F3, F4, and F5 are controlled operational tests and do not claim OpenAI behavior.
F2 contacts the real authentication boundary but does not prove that OpenAI inspected
or rejected any particular body. All five remain non-scoreable.

F1 passed on 2026-09-09 through a separately installed wheel with hash
`a7519afe7df26cc66ca94695e6e90be41723bb0b0e6b27c480af77f856702545`.
An independently signed source policy was deliberately presented alongside a target
policy differing only in its policy identity. The real `openai-conformance` command
retained canonical receipt
`6a0d132074a27272851ddc0affe08ba3ce096a59e0f7ff68dc450489080941bf`.
Its dedicated ledger remained empty, unchanged, and unblocked; the exact entry was
absent before and after; no credential, audit, normal output, container lifecycle,
provider request, reservation, retry, grading, scoring, promotion, or activation
occurred. [Milestone 79](MILESTONE_79_REVIEW.md) records the adversarial disposition.

The production command can now retain the exact F2 terminal tuple only when the
adapter, broker audit, and ledger independently agree on `authentication_error` at
`token_count`, absent spend, and null cost. Automated tests also prove that partial,
different, and post-reservation failures cannot mint that artifact. This is
instrumentation readiness, not by itself a live F2 pass;
[Milestone 80](MILESTONE_80_REVIEW.md) records that implementation disposition.

F2 subsequently passed through a separately installed wheel with hash
`6da01d8b82f5ac1de884be8c83e4daf351fdba84cfe7a0bdc3cbc7675d1bde17`
and immutable image
`sha256:711d60232e9f7c49da6a5e26ef2ec0b663f182f2f22b02731e679dc1dab74efe`.
The exact, independently authorized live token-count attempt terminated as
`authentication_error` at `token_count` and retained canonical failure artifact
`ee6cb8800a13985b38978d16b2d6cc54809fca23e6a1aa8930b0f466cb3bb3fa`.
Its dedicated ledger remained empty, unchanged, and unblocked; the exact entry and
both spend files are absent; generation was never requested; retry remains false;
and the container was removed on its first cleanup attempt. This result does not
prove that OpenAI inspected a particular body or establish provider billing.
[Milestone 81](MILESTONE_81_REVIEW.md) records the adversarial disposition.

F3 subsequently passed through the same separately installed reviewed wheel and
immutable image without an OpenAI credential or provider request. A precommitted
synthetic count caused the production spending controller to reserve 635 micro-USD;
the controlled response-stage disconnect then retained the full amount as
`uncertain` in dedicated disposable ledger
`70bae33b7b19656582d5f36c1bf669c2194d82e0adb83aa3e8b5e603e6296de7`.
Terminal audit outcome
`3e6b99a8e473ffecc28d940a3511f8f412d90a529f4790762dbc71534504b2ee`
records `transport_error` at `response`. No conformance artifact exists, retry and
automatic release remain false, and the container was removed on its first cleanup
attempt. This is a controlled local operational result and makes no claim about
OpenAI availability, receipt, token accounting, or billing.
[Milestone 82](MILESTONE_82_REVIEW.md) records the adversarial disposition. F4 and
F5 remain outstanding, so the overall gate remains open.

F4 subsequently passed through a separate installation of the same reviewed wheel
and immutable image, again without an OpenAI credential or provider request. A
syntactically valid controlled response carried precommitted synthetic usage but
deliberately invalid critique JSON. The spending controller settled 44 micro-USD in
dedicated disposable ledger
`a89d76056904c1eb7702b52deea22c5706be1592e8b6d17279bb5ae2d7da4233`;
the strict compiler rejected the response and retained status-`error` artifact
`16304946b61a491af26010f35350c2b24d1ced3b08f3a54f04b64ba11363098d`
with `invalid_response` at `validation`. No completed conformance result, provider
request ID, critique, usage claim, retry, automatic release, or promotion authority
was published, and the container was removed on its first cleanup attempt. This is
a controlled local validation result, not provider authorship, token accounting, or
billing. [Milestone 83](MILESTONE_83_REVIEW.md) records the adversarial disposition.
F5 remains outstanding, so the overall gate remains open.

F5 subsequently passed through another separate installation of the reviewed wheel
and the same immutable image, without an OpenAI credential or provider request. The
controlled launcher reached broker admission, persisted a 635-micro-USD reservation,
and exposed exact ledger entry
`e7eaea0ad124ca4be02e03febee9440740b4d42959ff61cf14f452756bfa6b60`
as `held` before it was terminated by SIGKILL. Independent watchdog result
`5166fca1bd66c9755ae6c82a6eb761830f2b0ca3f87077b930f6c73f5580a1a2`
removed exact container
`890bb4c6c1190c86c590d8910bcdc34cf6d85fedd9c9c0b1650c76278a480e30`
on its first attempt; a separate Docker lookup confirmed absence. Read-only recovery
reports phase `admitted` and ledger status `held`, with no terminal outcome, spend
receipt, conformance artifact, retry, or automatic release. This is a controlled
local launcher/watchdog result, not provider behavior or billing.
[Milestone 84](MILESTONE_84_REVIEW.md) records the adversarial disposition.

All 18 success positions and five failure boundaries existed after F5. At that
point, the overall gate remained open pending aggregate verification.

Deliberately ambiguous F3/F4 executions must use separately committed disposable
failure ledgers. Those ledgers are never reset, released, or reused for successful
probes. An unexpected violation in any live success run stops the whole OpenAI gate
pending a reviewed disposition and a new commitment.

## Gate output

The gate report must reverify all 18 success lineages and the five failure
artifacts from their authoritative sources. It must report exact attempt coverage and
fix provider authorship, billing reconciliation, quality, calibration conversion,
promotion, and routing activation to false. A separate reviewed converter may be
designed only after this report passes; routing remains disabled until the later
calibration and holdout gates pass.

That aggregate report passed offline on 2026-09-09. Its private sorted compact JSON
has SHA-256
`e58dc274b5087271fe1f241724fdd1f319956b4fffba8bf1e83e086db26ea72a`.
It reauthenticated all 20 retained successful exchanges from their authoritative
sources, counted exactly 18 qualifying positions, excluded the two invalidated
Astra/high successes, reverified F1 through F5, and represented every retained
failure, no-send event, expired preparation, and forbidden continuation. The
compiler accessed no credential and sent no request. All unsupported downstream
claims remain literal false. [Milestone 85](MILESTONE_85_REVIEW.md) records the
evidence and adversarial limits.

The separately reviewed offline converter subsequently consumed only the exact 18
qualifying receipts and artifacts named by this report. It emitted a private
18-of-360 partial calibration seed, not a gradeable `RawResultSet`, and made no
credential access or provider request. All complete-batch, quality, grading, scoring,
promotion, and activation gates remain closed. See
[Milestone 86](MILESTONE_86_REVIEW.md).

Changing the profile set, consecutive-success count, failure suite, or budget rules
requires a new public adversarial disposition before additional results are observed.

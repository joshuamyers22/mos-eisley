# Subscription inference qualification

Joshua Myers requested the next v1 blocker while publisher PR #290 merges. The browser login added by #289 delegates authentication to official clients, but it supplies no subscription inference adapter. This branch develops the missing boundary independently of application publication.

## Objective and acceptance

Admit an explicitly selected local ChatGPT/Codex inference route without copying credentials, silently using an API key, inheriting project execution authority or treating a model catalog as proof of entitlement. Preserve exact model/effort identity, bounded input/output and execution time, one-use Mos dispatch and cancellation without Mos replay. Keep existing qualified API routes and their immutable spend evidence separate. No study or sampling-store access is part of this work.

The first acceptance boundary is the official-client transport: inert imports, read-only account metadata and explicit compatible profile selection, explicit transfer and subscription-use consent, exact supported client identity, no prompt on status, strict event parsing, denied native tools, finite resources and cleanup. Saved conversation and coding integration must additionally bind the route and usage authorization through resume and pass their own exact-route qualification. A transport fixture does not close the overall v1 gate.

Selected production-template guidance: `AGENTS.md`, `docs/PYTHON_ENGINEERING_GUIDE.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`, `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`, `templates/WORK_NOTE.md`, `templates/THREAT_MODEL.md` and `templates/AGENTIC_VERIFICATION_LOOP.md`. Verification ceiling: one source/interface trace, focused adversarial boundary tests, one combined `make check`, then accountable disposition and a separately bounded live qualification. No paid inference or subscription quota use is authorized by the offline verification batch.

## Trust review

The official installed client owns authentication and refresh. Mos must not read its credential cache or return tokens/account email in diagnostics. Provider-origin and client configuration are a trust boundary: account sign-in is not permission to run tools, inherit plugins/hooks or dispatch an arbitrary model request. Subscription billing and quota semantics are distinct from API reservations; token counts must not be represented as verified zero-dollar billing or as inherited API capability evidence.

The official app-server documentation provides account/model discovery and explicit model/effort selection. Its model catalog can be bundled and does not prove entitlement. Real inference, cancellation, recovery and role capability need exact-route evidence. The local installed Codex client is version 0.161.0; its generated schemas remain disposable outside Git.

Sources: [Codex app-server](https://learn.chatgpt.com/docs/app-server), [ChatGPT-plan integration](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server), [authentication](https://learn.chatgpt.com/docs/auth), [configuration controls](https://learn.chatgpt.com/docs/config-file/config-reference).

### Assets, actors and abuse cases

Owner: Joshua Myers. Review trigger: a new subscription authorization and credential boundary. The local owner, installed native executable and provider service are trusted within their stated roles; project content and model output grant no additional authority. Host compromise and a malicious owner-selected executable remain outside the adapter's containment guarantee. Protected assets are native credentials, private prompts, workspace contents, subscription quota and attempt integrity. Input flows from stdin through a private native process to the provider; only admitted text and native usage return, with hashes retained in local receipts.

| Abuse case | Control and evidence | Residual risk / disposition |
|---|---|---|
| Project executable/configuration or prompt injection gains tools | Absolute non-project client selection; private cwd; ignored config/rules; disabled feature inventory; unexpected events rejected. Process and actual native fixture tests verify admission. | The selected native executable remains trusted; future client versions fail version admission. Owner review pending. |
| API credential fallback or credential disclosure | Environment allowlist, forced ChatGPT login and native login-status check. No cache access, prompt in argv, raw stderr or token-bearing receipt. Fake API-auth/secret-environment tests verify refusal. | Native authentication storage/refresh remains the client's responsibility. |
| Replay after uncertain dispatch or cancellation | Exclusive fsynced attempt/dispatch markers; existing attempt refused; owned process group terminated. Failure, timeout and cancellation tests verify no Mos replay. | Native retries and remote completion after cancellation can consume usage; local cancellation is not proof of zero charge. |
| Malicious response or resource exhaustion | Bounded input, stdout/stderr, deadline and returned text; strict event/usage/schema validation. Oversize, malformed, tool and usage tests fail closed. | Output/token ceilings apply after provider generation, not as billing guarantees. |
| Parent-directory substitution or receipt exposure | Owner-private non-symlink parent, exclusive mode-0600 files, mode-0700 attempt and durability barriers. Permission/symlink tests verify refusal. | A hostile same-user process can alter the owner's files; private-directory checks do not sandbox the owner. |
| Supply-chain compromise or service failure | Exact client version and explicit owner trust; no fallback provider; failed or ambiguous attempts remain burned. | Version identity is compatibility evidence, not a binary signature or service attribution proof. |

No residual risk has been accepted on behalf of the owner. Recovery preserves the uncertain attempt and requires a new explicit owner decision before another invocation. Monitoring consists of sanitized local completion/dispatch receipts; they cannot reconcile provider billing. No automatic quota purchase, retry campaign or operational activation is included.

## Implemented candidate

`mos subscription status` reads version and native login status without a prompt. `mos subscription ask` is an experimental, explicitly consented text route through Codex 0.161.0, currently admitting only `gpt-6-sol` / `medium`. The client owns credentials. Mos strips API-key environment variables, ignores project/user configuration and rules, uses a private temporary directory, disables native tools and rejects unexpected tool events. Strict structured output is supported through the provider interface.

A fresh attempt under an existing owner-private directory receives exclusive, fsynced request and dispatch markers. Completed, failed and cancelled attempts cannot be replayed. Receipts contain request/response hashes, route identity and native-reported token counts; they contain no prompt, response text or credentials. Cancellation terminates the owned process group. Input, event streams, returned output and invocation duration are bounded. These limits are not provider billing caps: the built-in OpenAI provider rejects retry overrides, so native transport retries remain possible. Token usage and account billing are unverified.

The 27 focused tests cover parsing, route admission, native authentication, stripped credentials/configuration, permissions, one-use attempts, structured output, stream limits, timeout and cancellation. `tools/smoke_codex_subscription.py` exercises the actual installed native client against a loopback Responses fixture with synthetic ephemeral authentication. It verified one fixture request, an empty tool inventory, exact requested model/effort and a completed text turn. The exact expected Code Mode disabled startup warning is admitted; other errors fail closed. The fixture does not prove account entitlement, provider attribution or coding quality.

PR #290 merged at `6e793eab37e57d3bcd2ca5d52a7fd52f340eeb10`; this candidate is rebased onto that baseline. The combined repository gate remains pending. No real inference, API spend, new account login or production activation occurred. Read-only native status confirmed an existing ChatGPT sign-in.

## Remaining acceptance

Accountable security review and separately approved, bounded subscription-use qualification must precede live probes. Verify actual text, strict JSON, cancellation and uncertain-usage recovery on the exact route. Saved conversation/resume and coding creator/critic/judge integration still require immutable route/authorization identities and their own qualification. Claude subscription transport and two-provider role qualification remain open. This experimental transport does not close the overall v1 subscription blocker or authorize a public release.

### Proposed live qualification scope (not authorized)

After the combined gate and owner review, propose at most three native inference invocations on the existing ChatGPT sign-in: one synthetic text request, one synthetic strict-JSON request and one cancelled synthetic request. Pin Codex 0.161.0, `gpt-6-sol` / `medium`, a 30-second inference deadline and an 8,000-byte returned-text ceiling. Use no real project/client data, API fallback or automatic quota purchase. These are invocation/output limits, not a service billing cap; native network retries can consume additional subscription usage. Preserve uncertain usage after cancellation. Recovery verification reopens local receipts and refuses the same attempt without another provider call. Stop on unsupported profile, unexpected native authority, account failure, malformed completion or a missing durable marker; do not replace a failed probe with a fourth request.

Accountable owner disposition must cover the trusted native executable, native-owned credentials, data transfer, quota exposure despite network retries, same-user filesystem trust and post-generation output limits. No independent reviewer or owner approval is asserted by this note. Record the exact reviewed commit and scope before live execution.

### Dependent integration

The existing saved conversation identity admits only recorded and OpenAI API modes. Live coding selections bind API spend policies and aggregate ledgers for every role. Subscription integration must add a distinct route/authorization identity, preserve it on cold resume and give each role its own one-use subscription admission rather than fabricating a dollar reservation. Tests must reject cross-route resume, changed authorization, expired scope and missing attempt state. Creator, child, two distinct provider critics and judge need exact-route functional qualification; this single compatible OpenAI text profile cannot satisfy that diversity requirement. Keep the existing API qualification valid for its original scope while these separate gates remain open.

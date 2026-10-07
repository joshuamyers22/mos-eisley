# Subscription inference qualification

Joshua Myers requested the next v1 blocker while publisher PR #290 merges. The browser login added by #289 delegates authentication to official clients, but it supplies no subscription inference adapter. This branch develops the missing boundary independently of application publication.

## Objective and acceptance

Admit an explicitly selected local ChatGPT/Codex inference route without copying credentials, silently using an API key, inheriting project execution authority or treating a model catalog as proof of entitlement. Preserve exact model/effort identity, bounded input/output and execution time, one-use dispatch and cancellation without retries. Keep existing qualified API routes and their immutable spend evidence separate. No study or sampling-store access is part of this work.

The first acceptance boundary is the official-client transport: inert imports, read-only account/catalog discovery, explicit transfer and subscription-use consent, exact supported client identity, no prompt on status, strict event parsing, denied native tools, finite resources and cleanup. Saved conversation and coding integration must additionally bind the route and usage authorization through resume and pass their own exact-route qualification. A transport fixture does not close the overall v1 gate.

Selected production-template guidance: `AGENTS.md`, `docs/PYTHON_ENGINEERING_GUIDE.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`, `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`, `templates/WORK_NOTE.md`, `templates/THREAT_MODEL.md` and `templates/AGENTIC_VERIFICATION_LOOP.md`. Verification ceiling: one source/interface trace, focused adversarial boundary tests, one combined `make check`, then accountable disposition and a separately bounded live qualification. No paid inference or subscription quota use is authorized by the offline verification batch.

## Trust review

The official installed client owns authentication and refresh. Mos must not read its credential cache or return tokens/account email in diagnostics. Provider-origin and client configuration are a trust boundary: account sign-in is not permission to run tools, inherit plugins/hooks or dispatch an arbitrary model request. Subscription billing and quota semantics are distinct from API reservations; token counts must not be represented as verified zero-dollar billing or as inherited API capability evidence.

The official app-server documentation provides account/model discovery and explicit model/effort selection. Its model catalog can be bundled and does not prove entitlement. Real inference, cancellation, recovery and role capability need exact-route evidence. The local installed Codex client is version 0.161.0; its generated schemas remain disposable outside Git.

Sources: [Codex app-server](https://learn.chatgpt.com/docs/app-server), [ChatGPT-plan integration](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server), [authentication](https://learn.chatgpt.com/docs/auth), [configuration controls](https://learn.chatgpt.com/docs/config-file/config-reference).

## Current state

Interface investigation is in progress. No provider inference, API spend, new account login or production activation has occurred. Accountable review is required before the new credential/authorization boundary is released. The publisher merge proceeds independently.

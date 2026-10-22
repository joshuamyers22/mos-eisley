# Experimental subscription sessions

A subscription session uses an explicit local usage authorization instead of an API spending policy. Native clients own sign-in and credential refresh. Usage reports are unverified; retries can consume quota or available credits. Invocation limits and returned-output limits do not cap provider billing.

Use existing owner-installed Codex 0.161.0, 0.162.1 or 0.163.0, or Claude Code 2.1.283.
Other versions remain inadmissible. Status reads native metadata without inference:

```sh
mos subscription status --provider openai_subscription --client /absolute/codex
mos subscription status --provider anthropic_subscription --client /absolute/claude
```

Start a subscription TUI directly from your project directory:

```sh
mos subscription chat --provider openai_subscription -C /absolute/project
mos subscription chat --provider anthropic_subscription -C /absolute/project
```

The launcher checks native sign-in and asks for transfer, subscription-use and
native-retry consent. It creates a fresh private authorization when you launch,
with four invocations, a ten-minute expiry, a 60-second invocation deadline and
the existing output limits. ChatGPT defaults to `gpt-6-sol` / `medium`; Claude
defaults to `claude-sonnet-5` / `high`. No prompt is sent until you submit a message.
`--client` selects an absolute trusted client; `--max-invocations`,
`--valid-for-seconds`, `--timeout`, `--model` and `--effort` select explicit limits
and an admitted profile. These limits do not cap native retries or provider billing.

Scopes and sessions live in owner-private `~/.mos-eisley-subscriptions` by default;
`--state-dir` selects a separate existing-parent location. The launcher displays
the session ID. Resume with the same provider, workspace and state directory:

```sh
mos subscription chat --provider openai_subscription -C /absolute/project \
  --resume SESSION_ID
```

Resume retains the original authorization, client digest, usage ledger and expiry;
it never renews a scope or clears uncertain usage. An expired or changed scope
refuses. Keep failure receipts for explicit recovery. Noninteractive callers must
provide all three existing acknowledgement flags: `--allow-data-transfer`,
`--allow-subscription-usage` and
`--accept-unverified-billing-and-native-retries`.

The following lower-level commands remain available for explicit role grants and
coding integration.

Create an existing owner-private directory for authorization and usage receipts. Choose a fresh 32-character hexadecimal session ID. The grant arguments are role, provider, exact model, effort, absolute native client and allowed invocation count:

```sh
mos subscription authorize --output /private/scope.json \
  --workspace /absolute/project --usage-root /private/usage \
  --session-id 0123456789abcdef0123456789abcdef \
  --grant chat openai_subscription gpt-6-sol medium /absolute/codex 4 \
  --max-invocations 4 --valid-for-seconds 600 \
  --allow-data-transfer --allow-subscription-usage \
  --accept-unverified-billing-and-native-retries
mos chat --subscription-authorization /private/scope.json \
  --allow-data-transfer --allow-subscription-usage
mos resume 0123456789abcdef0123456789abcdef \
  --subscription-authorization /private/scope.json \
  --allow-data-transfer --allow-subscription-usage
```

The saved session binds the complete scope, owner, workspace, native executable digest, authentication location and expiry. Resume requires the same authorization. Changed or expired scopes, missing usage history and uncertain dispatch fail before another invocation. Binary hashes bind the selected executable; they do not attest publisher authenticity. The authentication-location hash binds the local native context; it does not attest a remote account ID. Repository-inspection tools are unavailable on this experimental route.

`--live-coding-selection` and `--allow-live-coding` admit a separate `operator_subscription_session_coding` selection bound to the saved authorization. It has explicit creator, child, OpenAI critic, Anthropic critic and judge grants, protected source/test scopes, an exact Docker worker image and bounded Git integration. All roles share one invocation ledger. Two routes from one vendor count as one provider family. API ledger/pricing fields are forbidden in a subscription selection. See [the integration work note](SUBSCRIPTION_SESSION_INTEGRATION_WORK_NOTE.md) for the exact candidate profiles, verification and live qualification gate.

After a failed or cancelled native call, retain the authorization, reservation and dispatch receipts. Mos blocks further calls under that scope and refuses replay of the same call. Inspect ordinary private session/coding evidence and obtain a new explicit recovery decision; deleting markers or automatically issuing replacement authority is not recovery. Read-only inspection remains available. A fresh authorization does not silently replace an existing saved session's immutable identity.

The owner accepted the experimental security scope and the exact provider-diverse
synthetic qualification passed. [PR #291](https://github.com/joshuamyers22/mos-eisley/pull/291)
and [PR #292](https://github.com/joshuamyers22/mos-eisley/pull/292) merged through the
protected path; merged main `1d4d090` has the reviewed #292 source tree. The fresh
merged source and installed wheel each passed 109 focused checks. This closes that
experimental integration, while arbitrary-project quality, repeated-run reliability,
billing and native retry/generation limits remain unverified. These commands grant
no public production launch or additional inference authority.

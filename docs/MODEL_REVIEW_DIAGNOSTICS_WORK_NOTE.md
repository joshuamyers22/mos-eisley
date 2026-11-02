# ModelReview validation diagnosis and contract correction

- Status: implementation and offline verification complete; owner review pending.
  Owner Joshua Myers; operator Codex. Started 2026-11-02 UTC.
- Authority: add bounded redacted validation reasons, verify offline, run one
  freshly authorized 120-second probe, then fix the identified contract issue
  before any new signed candidate or full qualification.
- Base: main `8e7f2cb`; every frozen release and historical campaign stays
  unchanged. The earlier response body was not retained; its precise defect
  cannot be reconstructed from a hash or a Boolean.

## Guidance, invariants and evidence

Apply Python engineering, bounded verification and adversarial review guides,
work-note and threat-model templates. Add a strict fixed-size receipt to the
existing strict ModelReview decoder, including bounded reason/field enums,
input hash/size, JSON framing/root categories and subject-binding status.
Persist no response text, arbitrary field names, exception messages/contexts,
credentials, prompts or response bodies in diagnostics or Git. Model-generated
strings must never become diagnostic enum values without an explicit allowlist.

Keep duplicate-key refusal, strict fields/types, digest/decision/findings rules,
exact subject binding and creator/judge/integration ordering. A diagnostic
receipt supplies no acceptance, completion, repair, retry or machine authority.
Use the same validator in the actual coding path and the probe. Bound input,
error enumeration, emitted count values and serialization. Native transport and
one-use ledger gates remain unchanged.

Threats: untrusted output leaking through validation locations/context, silently
coercing or repairing malformed artifacts, duplicate-key override, stale subject
approval, uncertain-call replay and unsupported claims from one sample. Verify
these with synthetic offline fixtures and source/usage identity checks. Operator
technical review is not independent human security approval. Ordinary engineering
records establish no prospective evaluation eligibility; no sampling registry,
custodian mapping, label store or outcome store is read.

## Budget and stop rules

One combined code batch: focused contract/privacy/subject/order and subscription
authority tests, static checks and one full make check within four wall/monotonic
hours before publication; no concurrent local full gates. Preserve failures and
rerun only justified affected/unfinished stages. Required CI precedes normal merge.

After offline verification: exactly one fresh native probe, Claude Code 2.1.283,
Sonnet 5/high, 120-second native and 180-second outer wall/monotonic ceilings,
20-minute immutable grant, one invocation, 128,000 input bytes, 16,000 text output
bytes and 8,192 reported output tokens. Preserve actual HOME/native credential
selection and remove API keys. Use the retained synthetic rc.13 review packet
under a new workspace/grant/usage root; never resume an old slot. Fingerprint
all historical campaigns and freeze source/harness before dispatch. No API
fallback, model substitution, timeout increase, automatic retry, response repair,
renewal or replacement probe. Native billing/internal retries remain unverified.
Stop after this probe regardless of result. Fix only evidence-backed contract
issues and verify the fix offline before considering candidate delivery.

## Initial observations

The existing generic decoder collapses JSON/duplicate-key/schema/semantic
failures into one constant ValueError. Critic and judge subject binding is checked
separately, with no content-free reason receipt. The earlier standalone probe
retained only `critic_schema_valid=false` and a response hash; no exact defect is
recoverable from that record. This was the state before the probe below.

## Fresh bounded probe

Exactly one new native call completed on 2026-11-02 at 18:15:38 UTC under
the 120-second profile. One reservation, dispatch, native completion and usage
completion; 39.737 monotonic / 39.736 wall seconds. Native protocol validation
succeeded, with terminal result at 38.943 seconds and EOF 219 ms later.
No completion/exit stall reproduced. All eight prior evidence roots, 866 source
inputs and the private harness were unchanged before and after dispatch.

The strict shared validator rejected the 159-byte answer at the JSON boundary:
`invalid_json`, field `root`, prefix category `other`. No decision, findings or
subject could be parsed. This establishes a fresh non-JSON response, not a
decision/findings error or a timeout. No body is retained, so its exact wording
and the model's reason remain unknown; the older artifact's defect also remains
unknown. Answer SHA256:
`fcb6e1b3d7ca94af47c5fd22cd9e4c0177224580c617c89f23b01875dbb7e10b`.
Canonical request SHA256:
`121a207e96b424f848d55c01d2f1e09821fee206fed8665e80564635b70ea2f6`.
Probe source-manifest SHA256:
`6c27c81d61367876bc074639852bbacf30dd6a195ac3968ec659875ce33088bf`.
Private receipts remain under `.work/one-review-probe`; no response body was
written. Probe authority is exhausted; no repair, retry or second call follows.

## Evidence-driven corrections and limitations

The Claude adapter supplied its task instructions only inside a stdin JSON
document under the native client's default coding system instructions. Add a
static native system instruction that explicitly defines that envelope and the
requested JSON-only response. Task content remains on stdin, absent from argv
and diagnostic receipts. Keep one turn, empty tools, exact route, denied
permissions, strict final parsing, output limits and one-use ledger gates.
This corrects an ambiguous producer interface; the probe does not establish why
the model returned non-JSON, nor prove the changed producer's live behavior.
The advertised native JSON-schema mode is not enabled as an unverified protocol
change in this tool-free transport.

Separately, offline schema/runtime comparison proved the advertised ModelReview
schema accepted acceptance with findings and revision without findings while
runtime rejected both. Add mutually exclusive schema branches for those rules;
the strict runtime validator is unchanged. This is an independent reproducible
contract defect, not an inferred explanation for the fresh non-JSON response.

Diagnostics cover JSON framing, duplicate keys, strict schema reasons and exact
subject binding with fixed enums, at most 16 issues and 64,000 input bytes.
No arbitrary keys, values, messages, contexts or locations enter receipts.
Successful and failed actual coding reviews write the same bounded receipt.
Synthetic tests cover the rejection/privacy/binding gates and schema/runtime
agreement. Native mock tests verify envelope routing, private stdin content,
tool denial, one-turn limit and burned attempts. Live behavior after the fix,
new signed installation/upgrade and full workflow qualification remain unproven;
no candidate/tag/publication or new campaign is created by this one-probe task.

## Verification

Before the probe, 134 affected diagnostic/coding/subscription/qualifier cases
passed. After the correction, eight diagnostic and 17 Claude transport cases
pass. The final combined gate passes, as recorded below. A direct bare Pyright invocation selected the
wrong interpreter and reported missing dependencies; use the repository's
`uv run --frozen pyright` gate and retain that distinction.

All 25 coding workflow regressions also pass after the correction; repository
Pyright reports zero errors. The initial full gate was deliberately interrupted
after 57.051 seconds while source tests were running, to remove a global
no-clarification instruction that could unnecessarily affect ordinary chat.
Its exit -15 and log are retained under `.work/interrupted-instruction-gate`;
it is not reported as passing. Freeze the corrected 866 inputs and run the
combined full gate with the declared four-hour wall/monotonic limit.

The corrected frozen batch passes 3,927 source tests in 2,834.027 seconds
(17 skips), with 86% coverage, zero type/lint/format errors, verified runtime
export and successful source/wheel builds. Installed-wheel verification passes
2,914 tests in 2,001.074 seconds (13 skips). The full corrected `make check`
invocation exits 0 in 4,894.512 monotonic / 4,894.470 wall seconds, within both
four-hour ceilings. All 866 frozen inputs remain unchanged. Final log SHA256:
`063101cccc5eb9c6990a0c792d9c844d9d0e8e9884cef6d37d1bb7e7c7111a25`.
The earlier deliberately interrupted invocation remains nonpassing. No inference
was repeated during either offline gate. Owner review, a new signed candidate
and fresh installed live qualification remain pending.

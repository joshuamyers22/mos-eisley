# Live terminal chat boundary

- System: `mos chat --live-openai` and matching `mos resume` in the v1 TUI.
- Owner and accountable reviewer: Joshua Myers. This engineering change does not
  approve provider spending or production release.
- Scope: explicit transfer opt-in, saved session identity, token counting, response
  dispatch, shared spending admission, cancellation, and private artifacts.

| Asset | Need | Boundary and control |
| --- | --- | --- |
| API key | Confidentiality | Read from `OPENAI_API_KEY` at launch; never saved in the session, ledger, or artifacts. Fixed API endpoint, no environment proxies, no SDK retries. |
| Conversation text and memory | Explicit transfer | `--live-openai --allow-data-transfer` plus current policy, ledger and private artifact root are required. Token counting and generation both transfer admitted text. |
| Provider and pricing identity | Exact resume | Session stores model, effort, policy hash, ledger ID and artifact root. A mismatch fails before a turn starts. |
| Aggregate spend | Bounded local admission | Live chat requires a schema-2 policy that prices cache writes conservatively. Existing `BudgetedOpenAITransport` writes a reservation and uses the shared ledger before generation. Unknown outcomes retain exposure. |
| Saved turn state | No duplicate call | Controller persists running and consumes the attempt before awaiting the provider. Resume marks a running turn interrupted; only queued turns may run. |

| Abuse case | Control and evidence | Residual risk |
| --- | --- | --- |
| A recorded session silently becomes live, or vice versa | Persisted mode and exact resume identity; `tests/test_conversation_live_chat.py` | The local owner can create a separate session deliberately. |
| A changed price policy or ledger permits unreviewed exposure | Current policy hash, ledger identity and blocked status checked at launch and per turn; spend controller rechecks policy and reserves atomically | Reviewed prices are operator assertions; calls made outside this ledger are outside its cap. |
| A cancelled or crashed turn is retried | Attempt consumed before dispatch and exclusive artifact directory per attempt; cancellation test | Provider-side completion after interruption may still bill; inspect ledger and artifacts. |
| Text or key reaches another endpoint | Fixed OpenAI endpoint and bounded HTTP client; no tools, proxies, or SDK retries | A compromised local process or provider is outside the single-owner host boundary. |
| Malicious model output invokes local tools | No tool definitions or dispatcher in live runner; text only in the conversation controller | A user may still act on model text. |
| Artifact path substitution exposes receipts | Existing owner-only root and exclusive attempt directory; path checks in runtime | Trusted owner access can modify local files; checksums are not signatures. |

The output is a chat answer, not G2 qualification or release evidence. A live
credentialed validation and accountable security/spending review remain separate
from the offline tests in this change.

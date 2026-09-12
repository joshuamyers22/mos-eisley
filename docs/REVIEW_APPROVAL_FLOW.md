# Critic and judge approval flow

`BrokeredReviewApprovalFlow` connects a trusted host's approval UI to the
[brokered review controller](BROKERED_REVIEW_CONTROLLER.md). It presents exact
critic requests and aggregate spending before reservation, then separately
presents the verified findings and exact judge request. The flow supplies only the
hash returned by the UI to each controller operation. A preview is never copied
into the approval argument without that explicit UI decision.

The first `ControllerCriticPreview` contains all canonical model requests, the
spending envelope and the controller's review policy/deadline. It validates every
request hash against the envelope and the envelope against the controller
approval. Its total size is bounded before any prompt or spending. The second
`ControllerJudgePreview` is the existing evidence-bound controller output.

`TerminalReviewApproval` displays provider/model choices, reserved spending,
quorum, approval expiry and review time limit. `show` displays the full structured
preview. Approval requires `approve <exact hash>`; blank input, EOF, `cancel`,
`yes`, an incorrect hash or any other input declines. Judge approval is a second
prompt with its own hash. No default input approves a request. Full preview JSON
escapes control and bidirectional characters, and terminal labels/results use the
shared control-character sanitizer.

Hosts inject cancellable asynchronous input. For example, an already admitted
host can attach the adapter to an ordinary prompt-toolkit session:

```python
import sys
from prompt_toolkit import PromptSession
from prompt_toolkit.history import DummyHistory
from mos_eisley.review_approval_terminal import TerminalReviewApproval
from mos_eisley.run.review_approval import BrokeredReviewApprovalFlow

session = PromptSession[str](history=DummyHistory())


async def read_line(prompt: str) -> str:
    return await session.prompt_async(prompt)


ui = TerminalReviewApproval(read_line, sys.stdout)
flow = BrokeredReviewApprovalFlow(controller, ui)
result = await flow.run(
    critic_transports=critic_transports,
    critic_containers=critic_containers,
    judge_transport=judge_transport,
    judge_container=judge_container,
)
```

The host constructs the prepared envelope/controller and supplies its already
admitted transports and isolated containers. The adapter loads no credentials,
constructs no provider clients and adds no live CLI or terminal-mode activation.
Authorized credentialed conformance and the live launch/configuration gate remain
required. This increment delivers the approval interaction and controller
composition; it does not replace those admission decisions or relax the default
two-provider quorum. OpenAI-only synthetic tests explicitly select one provider.

Declining before critics creates no spending entries. Declining the judge retains
its existing allowance and creates no judge call. The judge prompt has only the
remaining whole-review time: time spent inspecting content counts, and expiry
cancels the pause while preserving holds. Initial approval cannot extend the
spending envelope's expiry. Cancellation during provider work awaits the owning
controller's complete child cleanup, including repeated cancellation. UI failures
cannot replay a completed operation. A stale competing flow cannot cancel another
flow's judge pause.

`run` returns the retained result or `None` after decline; lifecycle/validation
failures propagate. The result display preserves `infrastructure_error` as a
separate outcome. The flow is one-use, including after a display failure. Retain
`controller.start`, `flow.judge_preview.sha256` (when available), and the returned
result's digest independently for [stopped-run inspection](REVIEW_CONTROLLER_INSPECTION.md)
and [verdict verification](REVIEW_VERDICT_EVIDENCE.md). These are trusted host
outputs, not permission to restart an interrupted run.

Acceptance uses synthetic transports with a zero-dollar paid-provider budget.
Tests exercise the real asynchronous terminal input adapter, both approval phases,
decline and malformed input, expired prompts, changed evidence, UI errors,
competing flows, repeated cancellation and infrastructure-error display.
`tools/smoke_review_approval.py` repeats complete approval, judge decline and
repeated cancellation through real Docker workers and verifies every cleanup
receipt. It is included in `make container`; the source and installed-wheel suites
share the approval-flow tests.

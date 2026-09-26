# Adversarial review of the Claude Code feature survey

**Reviewed 2026-09-25.** Input: `~/Downloads/claude-code-features.md` (the
30-section feature guide supplied for this review). Comparison target:
[Mos Eisley plan](mos-eisley-plan.md) and [roadmap](ROADMAP.md). This is a product
comparison, not a claim that every guide entry exists in every Claude Code surface
or version. Anthropic's [overview](https://code.claude.com/docs/en/overview),
[security documentation](https://code.claude.com/docs/en/security), and
[checkpointing documentation](https://code.claude.com/docs/en/checkpointing) were
checked for the claims that affect the decisions below.

## Decision

Add three bounded product requirements to the
[version 2 plan section](mos-eisley-plan.md#31-version-2-conversation-and-automation-requirements):

| Addition | Why it helps | Placement and gate |
|---|---|---|
| Review launch preview | Makes the selected revision, omissions, policy, roster, spend ceiling and publication intent visible before an expensive or outward-facing run. Avoids accidentally reviewing stale or partial material. | V2 §31.1; reuse brief, policy, spending and publisher gates. No extra approval for an already-authorized review. |
| Exact file/range attachments | Lets a terminal user point to the evidence they mean without pasting a whole file or trusting a prose path guess. | V2 §31.2; after bounded reads and prompt attachments. Freeze bytes, digest and provenance; keep directory expansion explicit. |
| Scriptable `mos exec` semantics | A `--json` flag alone does not define how pipes, final status, stderr, cancellation or failed review behave in CI. | V2 §31.3; expand the documented CLI contract. Same controller and policy as interactive mode. |

These are post-v1 specifications, not implementation claims. They do not advance
G2 live review, execution permissions or an outward publisher.

## Survey against the existing plan

| Guide sections | Finding | Disposition |
|---|---|---|
| 1–5, 9, 16–17, 23–26: conversation, tools, commands, sessions, models, CLI | The core interaction is already in [§16.0](mos-eisley-plan.md#160-conversational-product-contract), with resume, queued steering, visible diffs and context controls. [§6.7](mos-eisley-plan.md#67-bounded-tasks-and-milestone-context-lifecycle) covers bounded context and explicit continuation. The three additions above make scope and automation contracts testable. | Adopt only the three gaps. Do not equate a command name with shipped capability. |
| 6–7: permissions, sandbox and plan mode | [§§9–10](mos-eisley-plan.md#9-execution-and-sandboxing) and [§23.1](mos-eisley-plan.md#231-release-blocking-contradictions) already go further than the guide's safety summary. Reading can leak secrets; a classifier or prompt cannot enforce containment. | No broad auto mode or blanket allowlist copied from the guide. Keep kernel boundary, role tiers, trusted policy and negative tests. |
| 8: `CLAUDE.md` and auto memory | [§16.0.2](mos-eisley-plan.md#1602-user-and-project-memory), [§17.6](mos-eisley-plan.md#176-bounded-project-memory-and-work-notes), and [§16.6](mos-eisley-plan.md#166-project-specific-points-of-view-and-best-practice-templates) already require explicit, scoped memory and guidance. Automatically saving inferred facts would create stale instructions and hidden cross-session data flow. | Retain curated memory and private task checkpoints; do not copy auto memory or recursive imports. |
| 10–15, 28: skills, agents, workflows, hooks, MCP, plugins and SDK | [§§13–14](mos-eisley-plan.md#13-mcp-client) and [§24.2](mos-eisley-plan.md#242-decision-matrix) already cover these with schema, provenance, isolation and extension gates. The guide's executable hooks, market downloads and inherited agents could run code or enlarge authority through a project file. | Keep typed, bounded handlers and capability intersection. Do not add arbitrary shell hooks, a general marketplace, or an SDK surface for parity alone. |
| 16, 19: rewind and worktrees | [§11](mos-eisley-plan.md#11-git-integration) and [§16.0.4](mos-eisley-plan.md#1604-repository-grouped-sessions-and-isolated-worktrees) cover worktrees. [§24.2](mos-eisley-plan.md#242-decision-matrix) explicitly defers per-turn undo. | Keep the deferral. An edit snapshot cannot promise to undo shell, subagent, external or concurrent changes. |
| 18, 21–22: background work, schedules, artifacts, browser and computer use | [§30](mos-eisley-plan.md#30-post-windows-embedded-terminal-emulator) already plans supervised local background terminals and notices. [§19.5–19.6](mos-eisley-plan.md#195-brokered-web-evidence-and-cache) covers brokered web and media evidence. Cloud routines, hosted artifacts, live browser control and desktop control imply new hosting, credential and egress boundaries. | No new release requirement. Reconsider only with a specific user task and separate threat, cost and quality evidence. |
| 20, 27: review, security review and CI | [§§15, 26](mos-eisley-plan.md#15-adversarial-review-pipeline) already define blind critics, judge, reproducibility and quality gates; [§12](mos-eisley-plan.md#12-github-integration) covers PR publication. Guide-style review levels or automatic PR posting could increase spend and false-positive exposure without improving correctness. | Use the launch preview and existing gates; do not add an `ultra` label, automatic posting or a second review pipeline. |
| 29–30: enterprise policy, telemetry and shortcuts | Trusted policy, owner-scoped telemetry and TUI controls are already planned in [§§16–17](mos-eisley-plan.md#16-cli-interface). A global analytics or shortcut parity target would add little to the core review outcome. | No new requirement. |

## Adversarial qualifications of the guide

1. **It is a feature inventory, not a release or security contract.** It mixes CLI,
   IDE, desktop and cloud behavior and states many claims without per-feature
   versions, prerequisites, availability or failure modes. Validate any proposed
   parity target against current official documentation and the exact surface.
2. **Its rewind description overpromises.** The guide says files are checkpointed
   before each edit. Anthropic documents a checkpoint when a prompt starts a turn,
   and says Bash, most subagent edits, external edits, linked paths and some queued
   steering are not restored. See [checkpointing](https://code.claude.com/docs/en/checkpointing).
   Mos Eisley should never advertise a complete undo without an effect ledger and
   recovery proof.
3. **Its safety language is too broad.** “Read-only,” “plan mode,” “auto mode,” and
   prompt-injection safeguards have different enforcement properties. Anthropic's
   [security documentation](https://code.claude.com/docs/en/security) itself notes
   that read-only Bash can read outside a working directory unless sandbox deny
   rules apply, and that no system is immune to prompt injection. For Mos Eisley,
   review blindness and confinement remain structural requirements.
4. **Convenience features have hidden authority and cost.** Hooks, plugin installs,
   MCP servers, browser sessions, cloud routines and automatic memory can execute
   code, expose credentials or persist unverified content. Parallel review, deep
   review and always-on automation multiply spend. Their value needs measured
   task outcomes under the same aggregate budget, not a parity checklist.
5. **Model-generated summaries are claims.** A subagent conclusion, review verdict,
   fetched page or generated artifact must retain source identity, omissions and
   uncertainty. The plan's frozen briefs and digest-bound evidence remain stronger
   than copying the guide's “only conclusions come back” pattern.

No feature in this survey warrants changing the existing security, storage,
evaluation, or review admission gates.

# Conversation `/diff` owner security review packet

Status: exact merged-`main` `/diff` feature release accepted for the scoped
owner-operated local use on 2026-10-04 UTC, after post-merge CI passed.

## Historical decision scope (2026-10-03 UTC)

- Candidate code: Git reader PR #253 at `2c2f67cce9f1b07bb9d19839c4f3a1d187071157`, panel PR #255 at `511fbbf2dd7723030bf76db10330fd82c8227e16`, and acceptance PR #256 at `c9ed00bb78cf51ff28c8606c5aa09f91e93de7ed`. The three PRs are stacked and remain draft.
- Use: an owner-operated local TUI inspecting the selected Git workspace and explicitly sending bounded selected-line attachments through ordinary conversation admission.
- Review basis: plan §16.4.1, `CONVERSATION_DIFF_PANEL_THREAT_MODEL.md`, `CONVERSATION_DIFF_GIT_FOUNDATION.md`, and `CONVERSATION_DIFF_ACCEPTANCE_VERIFICATION.md`. Selected review guidance: `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`, `templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`, and `templates/THREAT_MODEL.md`.
- Excluded decisions: provider-spend approval, Git mutation authority, merge, and release. This review cannot grant them.

## Historical technical assessment

| Boundary | Evidence inspected | Assessment |
|---|---|---|
| Workspace and Git execution | `GitWorkspaceReader` binds the selected directory, checkout root, Git directory and executable identity; uses fixed argv, a minimal environment, helper overrides, path admission, byte/file/time caps, and stale snapshot checks. The real-checkout tests cover hostile helper configuration, out-of-scope/unsafe paths, symlinks, limits and index nonmutation. | The ordinary static hostile-repository case is controlled. The same-user race below remains. |
| Patch to terminal | The panel renders untrusted labels and patch content through `display_text`, discloses incomplete inventories and partial patches, and never previews untracked file content. | Terminal control bytes are escaped before display; Unicode lookalikes and source meaning remain untrusted. |
| Selection to prompt | Selection is limited to visible lines within one hunk, 40 lines and 2,048 bytes per attachment, at most three attachments. The excerpt and source digests are frozen, shown in the composer, and rechecked against a fresh snapshot and patch before queueing. | Stale or wrong-workspace attachments are refused, retaining the draft. A final-check-to-queue race remains possible under same-user filesystem mutation; the admitted bytes remain frozen. |
| Conversation authority and persistence | Selection alone changes local composer state. The normal message path requires explicit send, enforces the 8,000-character/256-line aggregate limit, stores attachment provenance with the admitted turn, and labels JSON source as untrusted in the model context. | No new review, edit, or provider authority follows from selection. Source instructions can still influence a model; chat mode and its policy govern any subsequent provider use. |
| Refresh and switch | Git reads run off the UI loop. Generation/workspace checks discard obsolete results; directory switch rejects a draft or attachment. The PTY and concurrent-edit acceptance checks exercise those flows. | Reads are sequential within one poll cycle. Cancellation does not terminate an already running thread; rapid restarts can overlap bounded reads. |

## Historical findings and residual limits

1. **Same-user Git configuration race — scoped residual, potentially high consequence.** Helper keys are read and overridden before a later Git status/diff call. A process that can rewrite local Git configuration between those calls might introduce a new helper key that executes during the read. The reader checks configuration changes across the snapshot and rejects a changed result, but that check occurs after the Git command. A same-user process can also race workspace files after final attachment verification. This is outside an OS-isolated security boundary. The owner must accept this only for the documented trusted local owner/workspace scope, or require process isolation before broader use. Evidence: `conversation_git.py` `_helper_config_keys`, `_command`, `snapshot` and the foundation threat model.
2. **Overlapping canceled reads — low availability residual.** `restart_diff_poll` cancels the coroutine, while an active `asyncio.to_thread` call continues until its Git operation finishes. Repeated rapid restarts can create overlapping, individually bounded reads and postpone a fresh view. The generation check prevents obsolete display/admission; the Git reader caps output and applies a five-second deadline per Git process. This should be monitored or serialized before treating the panel as resilient to adversarial local input floods. Evidence: `conversation_tui.py` `restart_diff_poll`, `poll_diff`, and `conversation_git.py` `GIT_DEADLINE_SECONDS`.
3. **Model interpretation of source — expected residual.** The frozen excerpt is JSON escaped and explicitly labeled untrusted, but model behavior is not a strict parser or authorization boundary. Existing conversation policy continues to control actions and spend.

No release-blocking defect was found within the owner-operated local scope above. That conclusion is an agent technical assessment, not an accountable owner acceptance.

## Historical hardening path

1. **Before widening the local trust scope:** put Git reads behind an OS-enforced process boundary that prevents repository-controlled helpers from executing and denies network access. Test a concurrent rewrite of `.git/config` and `.gitattributes` while reads run, and assert that no marker command executes. Git's documented configuration controls skip system/global files, while repository-local configuration is read by default; adding more scanned override keys alone cannot close the time-of-check/time-of-use race. See [Git configuration](https://git-scm.com/docs/git-config) and [Git attributes](https://git-scm.com/docs/gitattributes).
2. **Availability improvement:** use one dedicated, coalescing Git read worker per TUI. Keep at most one operation running and one latest refresh request pending; canceled generations discard results, but do not create another concurrent read. Add a rapid-toggle test that measures the maximum active read count and checks the latest workspace result.
3. **Attachment and model safety:** keep the frozen bytes and send-time verification, show the owner the exact excerpt and destination at send, and enforce edit/review/spend authority in code outside the model's interpretation of the excerpt. Add an adversarial source-instruction test to the conversation policy suite. For a workspace with an untrusted concurrent writer, use an immutable captured source or require explicit reattachment after a detected change.

The [attachment authority follow-up](CONVERSATION_DIFF_ATTACHMENT_AUTHORITY_WORK_NOTE.md)
implements the send-time view and adversarial policy test on a later stacked
candidate. This is technical evidence for condition 3, pending exact-candidate
accountable review; it does not expand the accepted local trust scope. The
untrusted-concurrent-writer limit in condition 3 remains.

These are recommendations for later work. The owner decision below concerns the exact current candidate and scope, not an assumption that these improvements already exist.

## Historical verification and limits

- The final elevated `make check` on PR #256's exact source passed Ruff, Pyright, 2,670 repository tests (4 skipped), export verification, build, and 1,918 installed-wheel tests. Earlier sandbox socket errors and two intermittent review fixture failures are recorded in `CONVERSATION_DIFF_ACCEPTANCE_VERIFICATION.md`; no source changed before the passing full run.
- During this review, focused stale-attachment and directory-switch tests passed, and the hostile-helper real-checkout test passed after correcting a mistyped unittest class name in the invocation. No product source changed during this review.
- PR #253 and #255 checks were green at review time. PR #256 source and package checks were still in progress when checked; its container and secret-scan checks were green. Refresh CI before merge.
- This review did not run an OS process sandbox or a concurrent config-race exploit, and does not assert security against another actor with the same user's filesystem/process authority.

## Historical accountable owner decision

Repository `AGENTS.md` requires accountable review beyond an agent's own assessment for security and release decisions. On 2026-10-03 UTC, the accountable owner accepted this exact candidate for a **trusted local owner-operated workspace**, with the following conditions stated in the conversation:

1. Track the Git read isolation and concurrent configuration-race test in the hardening path above before expanding the trust scope.
2. Track the coalescing single-worker refresh and active-read concurrency test before expanding the trust scope.
3. Track the attachment destination/authority and adversarial source-instruction checks before expanding the trust scope.

This packet is the tracking record for those conditions. Broader use with an untrusted concurrent local writer is outside the accepted scope until the applicable hardening is implemented and reviewed. The acceptance binds the code commits listed in **Decision scope**; documentation-only edits to this packet do not change that code scope. This security decision does not approve merge, release, Git edits, provider use, or provider spending.

## Exact merged-`main` release candidate (2026-10-04 UTC)

The current `/diff` code is `main` commit
`9822de630bc7b77d146f7edac4604aec6780daa3`, source tree
`0bcc199ed98dbdfef6529fe565416127e86fe272`. PR #267 merged the
Git-isolation commit `3b2d9f0`, the single-worker follow-up `bd68450`
(stacked PR #269), and attachment-authority follow-up `b225fcf` (stacked
PR #271). The owner accepted #269 and #271 for scoped merge after review; the
owner's direction to close #267 authorized its merge. Those decisions did not
approve `/diff` release or expand the historical trusted-local scope.

The proposed feature-release scope is the **owner-operated local conversation
TUI on macOS or Linux hosts where the OS Git-isolation probe succeeds**, for an
owner-selected workspace. `/diff` shows bounded tracked staged/unstaged patches
and path-only untracked entries. The owner explicitly confirms complete frozen
excerpts and the recorded/live chat destination before an attached turn is
queued. Live chat still requires its separate policy and spending authority.
Unsupported hosts, including unqualified native Windows, refuse Git reads
rather than falling back to unconstrained Git. This decision does not release
the whole v1 product, authorize public activation, provider spending, Git
writes, or operation against an adversarial same-user process able to replace
trusted application or Git bytes.

### Disposition of the three original hardening conditions

| Historical condition | Current control and exact-candidate evidence | Remaining limit |
|---|---|---|
| Concurrent Git configuration could select a helper after key scanning | Every Git call crosses a mandatory macOS Seatbelt or Linux `no_new_privs`/seccomp process boundary with network and child-process denial; a concurrent `.git/config`/`.gitattributes` rewrite runs a marker helper without confinement but cannot execute it during the confined read. The real-checkout and isolation suite passed 16/16 on merged `main`. | A Git read is not an atomic filesystem snapshot. A compromised trusted Git binary or same-user replacement of trusted application/Git bytes remains outside the boundary. A host without working isolation fails closed. |
| Canceled refreshes could overlap active reads | One TUI-owned worker keeps at most one Git read active and one latest refresh pending. The rapid-refresh test records a maximum active count of one and the final workspace result; the merged-`main` `/diff` suite passed 19/19. | An in-flight read can occupy the worker until its bounded deadline; obsolete results are discarded. |
| Selected source could obscure destination or induce review/tool/spend escalation | A scrollable send review shows the complete frozen excerpts, destination, session and draft; a second explicit send is bound to those bytes. A changed draft requires a new review and cancellation preserves it. The adversarial source-instruction test keeps malicious diff text in ordinary tool-free user content, with no structured review or provider escalation. | Model interpretation of untrusted text is not a parser or authorization boundary. A same-user writer can change workspace files after the final source check; the admitted excerpt remains frozen. Live provider admission and spend remain separately controlled. |

### Exact-candidate verification and residual-risk assessment

The [merged-`main` acceptance record](CONVERSATION_DIFF_ACCEPTANCE_VERIFICATION.md)
reports 57/57 focused tests across real PTY/panel/attachment, Git/isolation and
conversation TUI suites. PR #267's exact head passed source, package,
container, Windows-file, quality and secret-scan GitHub checks; the merge commit
has the same source-tree hash. Post-merge `main` CI run `37227504789` passed
source, package, container, Windows-file and quality, and the separate secret
scan passed. The documentation-only release-record branch based on that main
commit passed elevated `MOS_REQUIRE_TMUX=1 make check`: Ruff, formatting,
strict Pyright, 2,724 source tests (4 skipped), export verification, wheel
build and 1,978 installed-wheel smoke tests. No product code changed.

No in-scope blocker was found in that technical evidence for the proposed
trusted-local feature scope. This is an agent assessment, not accountable owner
release approval. Residual risks requiring owner disposition are: (1) trusted
application/Git binary and same-user filesystem races, including after the final
attachment check; (2) the model's possible misreading of source instructions
despite code-enforced authority separation; and (3) host support limited to
working macOS/Linux isolation. The narrower scope does not protect against an
untrusted concurrent writer with the owner's process and file privileges.

### Accountable owner release decision

**Accepted for the stated scope.** On 2026-10-04 UTC, Joshua Myers reviewed
this exact-main security packet and the 57-test acceptance record, then chose
“Accept scoped `/diff` release once CI passes.” The decision binds feature
code at `main` commit `9822de630bc7b77d146f7edac4604aec6780daa3`
and source tree `0bcc199ed98dbdfef6529fe565416127e86fe272`. It accepts
the residual risks stated above for the owner-operated local TUI on macOS/Linux
hosts where Git isolation succeeds. Post-merge `main` CI passed all checks, so
the owner's condition is satisfied and this `/diff` feature gate is closed.

This decision does not approve whole-product v1 or public launch, provider
requests or spending, Git writes, native Windows support, or an adversarial
same-user writer. A later product-code change, different host boundary, or
expanded trust scope requires fresh qualification and accountable review.

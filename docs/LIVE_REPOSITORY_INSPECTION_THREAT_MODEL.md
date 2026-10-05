# Live repository inspection threat model

## Scope and ownership

- System: opt-in `--live-repository-read` and per-turn `/inspect ` in the owner-operated macOS/Linux TUI.
- Owner: Joshua Myers. This implementation record grants no release, provider spend, or public activation approval.
- In scope: three read-only tools, selected-workspace confinement, transfer to the existing OpenAI live chat policy, saved session identity, and local spending admission.
- Outside scope: Git commands, filesystem writes, shell execution, background indexing, native Windows, and an adversarial process with the owner's filesystem privileges.

## Assets, actors, and boundaries

| Asset | Need | Boundary |
| --- | --- | --- |
| Workspace files | Confidentiality and integrity | Only an explicit `/inspect ` turn in a session saved with the read opt-in can expose bounded visible UTF-8 content. Descriptor-relative traversal refuses symlinks, hidden paths, special files, and escapes. |
| API key | Confidentiality | Existing owner-provided environment credential and fixed OpenAI endpoint; tools have no environment access. The owner must keep key files outside the selected visible workspace. |
| Spending ledger | Bounded exposure | Every model response in a tool turn creates its own exclusive reservation and receipt under the current schema-2 policy and shared aggregate ledger. |
| Saved conversation | No implicit retry or escalation | The opt-in is saved in `LiveChatIdentity`; the controller burns an attempt before dispatch, and resume checks exact identity. |

The local owner selects the workspace and opts into provider transfer. The provider
may propose only `repo_list`, `repo_search`, and `repo_read` with their fixed schemas.
The dispatcher performs no writes or commands. Tool output is marked untrusted and
bounded; the system instruction tells the model to cite source paths and lines.
Successful source references are also appended deterministically to the answer.

## Abuse cases and controls

| Abuse case | Control and evidence | Residual risk |
| --- | --- | --- |
| A normal live turn or resumed session silently gains tools | Saved opt-in, exact resume identity, and explicit typed `/inspect ` command required; the saved turn records authority. Pasted or literal command text remains inert. Offline terminal, controller and runtime tests. | The owner can deliberately opt in and request a read. |
| Traversal, symlink, FIFO, or workspace replacement crosses the path boundary | Descriptor-relative traversal with `O_NOFOLLOW`, regular-file checks, pinned workspace device/inode per runtime launch, fixed path grammar, before/after file metadata checks. Workspace identity is checked before and after counting and before generation. Offline refusal, change and replacement tests. | Same-owner adversarial mutation is outside scope; hardlinks are not excluded. |
| Huge trees or files consume resources | List 80 entries; scan 1,024 directory entries; search 64 files/64 directories/depth four/20 matches; file 64,000 bytes; result 8,000 bytes; five provider responses and six read calls. Incomplete searches report truncation and skipped files. Offline bounds tests. | Local filesystem operations can still be slow on untrusted network mounts. |
| Source text instructs the model to escalate tools, spend, or reveal secrets | Source is labelled untrusted; fixed tool catalog and dispatcher reject unknown tools; spending controller checks exact catalog before counting or dispatch. Offline hostile-source and unknown-tool tests. | Model answers can still be influenced by adversarial source prose. Owner should verify consequential claims. |
| Tool history or later responses evade spending admission | Each response receives independent token counting, current policy check, reservation, shared-ledger entry, and receipt. Unknown outcomes retain exposure. Offline two-response settlement test. | Provider-side billing after cancellation remains uncertain; shared ledger covers only traffic routed through it. |
| A file contains sensitive material | Hidden paths and the project's `private/` components are refused, including during recursive searches. The owner selects the workspace. Only bounded excerpts are transferred. | Other visible files may still contain secrets; the owner is responsible for choosing an appropriate workspace and prompt. |

## Decisions

- Joshua Myers accepted the implementation controls and residual risks on 2026-10-04, conditional on gates passing, for code scope `ed453675e12205d3eac17438f08602b0e3f51b3a802480d1c04195e99864b5a7`. The condition was satisfied by the completed gates on 2026-10-05 UTC. See the [owner decision](LIVE_REPOSITORY_INSPECTION_OWNER_REVIEW.md). This approves no live spend, merge, or release.
- Credentialed validation requires a separately approved, current policy and aggregate spend cap. Offline tests send no provider requests.
- Any broader use or trust scope requires a new review of path and source-instruction risks.

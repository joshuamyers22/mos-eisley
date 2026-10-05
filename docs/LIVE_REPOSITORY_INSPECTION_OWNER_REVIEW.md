# Live repository inspection: owner security and spending review

## Candidate and decision

- Candidate: local `feat/live-repository-inspection`, based on `main` at `5a6be4eff5470cf186cb7032b76598b5b0c1c20c`.
- Exact code and test inventory: [candidate manifest](LIVE_REPOSITORY_INSPECTION_CANDIDATE.json). The manifest binds the base commit and the full SHA-256 of each changed Python file. Changes to those files require a refreshed review.
- Accountable owner: Joshua Myers. Decision: **accepted**, 2026-10-04, for code scope `ed453675e12205d3eac17438f08602b0e3f51b3a802480d1c04195e99864b5a7`, conditional on gates passing. The owner's explicit reply was “Accept implementation if gates pass.” That condition was satisfied on 2026-10-05 UTC: combined `make check` exit 0; 2,737 source tests run with 4 skips; 1,995 installed-wheel tests passed; final affected tests and static checks passed.
- Scope proposed for acceptance: implementation controls for explicitly authorized read-only turns in trusted owner-operated local macOS/Linux workspaces. Local verification is on macOS; Linux CI and credentialed validation are separate evidence.
- This packet grants no provider spend, policy approval, merge, release, or broader activation.

Repository [AGENTS.md](../AGENTS.md) requires accountable review beyond an agent's own assessment for security and financial logic. Codex's assessment below is implementation evidence for that decision.

## Implemented authority and data flow

1. Launch and resume require the same saved `--live-repository-read` profile and the existing live transfer/spending options.
2. A typed `/inspect QUESTION` command records explicit turn authority. Pasted or literal text does not. Ordinary turns retain no tools.
3. The model sees exactly three function schemas: list, literal search, and bounded read. Every local call traverses descriptors beneath the pinned selected workspace; hidden and `private/` paths are excluded. No shell, Git, edits, or writes are available.
4. Returned file bytes are labelled untrusted data. Successful sources are appended to the answer. File metadata and workspace identity checks refuse observed changes.
5. Every model response counts the exact input, checks the current schema-2 policy, and reserves in the shared aggregate ledger before generation. Follow-up responses have separate receipts. Cancellation and uncertain outcomes retain exposure; there is no automatic retry.

Limits: five model responses and six local calls per turn; 80 listed entries; 1,024 entries examined per directory scan; 64 searched files and 64 directories to depth four; 20 matches; 64,000 bytes per file; 80 read lines; 8,000 bytes per tool result including its label. Incomplete results are marked.

## Verification and finding disposition

See the [work note](LIVE_REPOSITORY_INSPECTION_WORK_NOTE.md) for commands and full-gate results, and the [threat model](LIVE_REPOSITORY_INSPECTION_THREAT_MODEL.md) for scope and abuse cases.

| Finding challenged | Disposition and evidence |
| --- | --- |
| A pasted command prefix could authorize reads | Corrected: explicit saved turn flag, terminal literal handling, JSON and SQLite persistence checks. |
| Continuation history could enable different tools or evade the ledger | Fixed tool-catalog equality, bounded matched call/output history, one reservation per response. Hostile-source escalation fails before another provider request; a tight aggregate cap denies follow-up generation. |
| Workspace replacement during token counting could dispatch against a stale selection | Runtime reader pins device/inode; checks before/after counting and before generation. Replacement test observes no generation or ledger admission. |
| Provider SDK reasoning history includes optional fields | Corrected to accept its nullable content/status fields while retaining the exact tool catalog. SDK-shaped offline fixture completes a two-response read turn. |
| Result labels or invalid starting lines could defeat output/reference claims | Label is inside the byte ceiling; out-of-range lines refuse; empty files reference the file itself. Encoded output and reference tests pass. |
| Visible `private/` directories could expose established local credential and attestation storage | Excluded by the path grammar and by list/search traversal. A synthetic private-file fixture is absent from listing/search and refuses direct reads. |

Assessment: the implemented controls support the proposed trust scope, subject to the completed gates and the owner's decision. This is one agent's assessment, not independent security certification.

## Residual risks for the owner to decide

- Other visible files can contain secrets even with hidden and `private/` paths excluded. Selecting a workspace authorizes bounded transfer of its permitted visible content, not just the filename mentioned in the question. Keep credentials and confidential material outside that scope.
- Hardlinks can expose regular-file bytes originating elsewhere. Adversarial activity with the owner's filesystem privileges is outside the guarantee; ordinary changes are detected when metadata or workspace identity differs.
- Hostile source prose can influence an answer. It cannot add executable tools or remove admission caps. Source references identify accessed content; they do not establish that every model claim is correct.
- Reads are bounded by bytes and traversal counts, but a slow filesystem can still stall local operations. The scope excludes malicious or untrusted network mounts.
- The aggregate ledger covers traffic routed through this runtime. Provider billing after cancellation can remain uncertain and retains its reservation.

The owner accepted these controls and residual risks for the stated implementation scope once gates passed. A later live validation requires its own reviewed policy, current prices, chosen synthetic workspace and explicit aggregate cap.

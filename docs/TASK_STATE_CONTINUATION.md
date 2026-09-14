# Explicit fresh-context continuation

G1 fresh continuation lets one new recorded conversation claim one explicitly
selected outstanding work unit from a closed checkpoint. The boundary lives in
`src/mos_eisley/task_state_continuation.py`; it uses the G0
`ContinuationSelection`, the immutable archive selected by the current task-state
pointer, and a separate private claim file. The archive store derives the claim
filename from the owner/project scope and selected work-unit identity/revision;
choosing another filename cannot claim the same work twice.

The selection must copy the exact owner/project scope, checkpoint identity and
digest, outstanding work-unit reference, checkpoint workspace, selected unit's full
required-input inventory, cumulative-context baseline and task-ledger baseline. It
grants no authority. Supplying that selection is the explicit request to continue;
the controller does not ask for a second confirmation.

Launch a new recorded conversation with the two private selections:

```sh
mos --plain -C /path/to/project \
  --task-state-selection /path/to/current-task-state.json \
  --task-state-continuation-selection /path/to/continue.json \
  --task-state-storage /path/to/private/task-state-archives
```

The selection and current pointer are pinned by their exact launch bytes. Their
files and parent directories, and the claim directory, must be owner-only. An
unclaimed continuation refuses an existing conversation: its first claim must use a
fresh session. A crash-recovered resume may reuse the exact claim only with the same
session identity, selections and live-freshness digest.

## Freshness and bounded context

Before the claim, the controller fully replays the selected archive and reproduces
the G0 continuation validation. It therefore cannot change the checkpoint revision,
select terminal or non-outstanding work, start a unit with incomplete dependencies,
replace required inputs, or reset cumulative
context, spend, attempts, correction/review counters or uncertain-effect counts.
The fresh context retains the checkpoint's full outstanding-work references, active
decisions, lineage and short next-action view; it does not receive ambient history
from the older conversation.

Required input digests must match recovered archive artifacts or currently inspected
main files. Missing required bytes stop before the claim. The default inspector
reads Git without changing the index or working tree. It
checks repository identity, branch, `HEAD`, the `HEAD` tree, a bounded binary diff,
bounded untracked-file names/content, and availability/digests for checkpoint main
files. It disables external diff/text conversion and filesystem-monitor commands.
Every observation is bounded; overflow, symlink paths, non-UTF-8 Git
names or command failure stops the claim.

The runtime evidence compares all five workspace dimensions and lists exact
blockers. If any dimension changed, every historical passing checkpoint verification
is listed as stale. That stale overlay supersedes the archived pass for current use;
the immutable checkpoint is not rewritten and the old result is not silently
presented as current. Missing main files make freshness readiness false; unrecoverable
required inputs or missing archive evidence stop acquisition. This boundary detects
and discloses mismatches; it
does not automatically run tests or invent replacement evidence.

## Atomic one-session claim

After validation and live inspection, the controller takes a private sibling lock
and atomically creates a canonical claim binding the session, both selection
digests, archive/checkpoint revisions, selected work unit and freshness digest. A
different session, changed selection, conflicting claim or concurrent claimant fails
closed. The selections and live workspace are checked again after the durable claim,
before recorded-model dispatch. An exact same-session retry is idempotent.

The first claim fixes its freshness digest. A subsequent workspace change stops
reuse of that claim; recording a revised checkpoint and selecting a revised work
unit is required before a new handoff. The separate
[changed-tree replacement-verification boundary](TASK_STATE_REPLACEMENT_VERIFICATION.md)
can close the claimed queued or active unit only when newly supplied passing evidence
binds that exact claimed workspace and input state. The archived task ledger is the
preserved baseline; it does not replace the dispatch spending/approval boundary.

The claimed continuation is persisted in the request's bounded temporary task-state
artifact and text-free admission. It may be inspected with `/context`. The claim
never replays an uncertain operation, revives an approval, enables a tool, grants
credentials/spending, or supplies execution authority; the recorded controller's
tool-call limit remains zero.

## Acceptance

`tests/test_task_state_continuation.py` covers exact and idempotent claims,
duplicate/concurrent sessions, fresh-session enforcement, changed pointers and
selections, alternate claim filenames, incomplete dependencies, context/ledger
resets, mid-claim workspace races, missing main files and required input bytes,
stale-verification disclosure, forged overlays, private storage, conversation
admission and real tracked/untracked Git changes. These fixtures establish boundary
enforcement, not live-provider quality. The separate replacement-verification
acceptance demonstrates a successful check and atomic closure on a changed workspace.

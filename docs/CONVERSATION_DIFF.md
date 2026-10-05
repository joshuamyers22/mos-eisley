# Live diffs and retained review findings

The Git-review/findings panel uses `mos --git-review-panel` (or the same option
on resume). Ordinary `mos` retains the qualified workspace diff panel. Both use
the same session controller; frozen attachment formats retain their provenance.


`/diff` or F10 toggles a read-only diff pane in the conversation TUI. It uses the
trusted [local Git/read broker](GIT_REVIEW_SCOPES.md) at the session's explicit
POSIX repository root. At 110 columns or wider, conversation and diff appear
beside each other. Narrower terminals show the focused pane. Tab cycles through
the composer, conversation and diff without discarding the draft. Opening the
panel never starts a model request or changes the checkout.

The file list distinguishes staged, unstaged and untracked inputs, with added and
removed source-line counts. The basis is HEAD → index → working tree; an unborn
HEAD is labelled. Renames appear as deletion/addition paths, preserving both
versions without guessing a line mapping. Empty trees, deleted files and empty
files have explicit views. Protected, binary, oversized and unavailable inputs
have omission labels. Non-Git directories and linked worktrees are unavailable.

## Navigate and refresh

With focus in the diff pane:

| Control | Action |
|---|---|
| Up/Down, Page Up/Down and mouse | Navigate/select the displayed source. |
| Ctrl-N / Ctrl-P | Choose the next/previous file; Ctrl-N reaches subsequent file pages. In the findings list, choose the next/previous finding. |
| Ctrl-R | Refresh the live comparison, leaving historical evidence view. |
| Ctrl-E | Expand the next bounded chunk of patch rows. |
| F11 | Attach the selected source rows, or the source row under the cursor. |
| F12 | Load retained review findings. |
| Enter in the findings list | Open the selected finding's historical source and exact coordinates. |
| F10 | Hide/show the diff pane. |

Git reads run outside the UI event loop. While visible, the panel polls every two
seconds. Refresh requests coalesce; one read runs at a time, and obsolete
generations cannot publish. Acquisition reads twice and rejects changing inputs.
File selection and source coordinates survive refresh where available. A changed
source clears an unfinished mouse/keyboard selection with a notice; already
attached bytes stay frozen. Failed refreshes retain the prior snapshot behind an
explicit stale label. Switching directories discards the old refresh generation;
unsent source attachments must be submitted or removed before switching.

A page initially includes at most eight files and shrinks further if needed to
stay under the existing 64 KB scope ceiling. Files retain the 16 KB source limit.
Each displayed patch chunk contains at most 400 rows. Partial file lists, clipped
views and omitted sources are disclosed; expansion never lifts the source/read
limits. Metadata inventory, Git output and execution time retain the broker's
bounds, with external diff, textconv and filesystem monitor helpers disabled.

## Frozen prompt attachments

Select source rows with the keyboard or mouse and press F11. The composer shows
the workspace, literal path, staged/unstaged/untracked basis, original old/new
line ranges and snapshot digest. Alt-Backspace removes the latest attachment;
Ctrl-U discards the draft and its attachments. Selection alone does not send.

Attachments retain exact patch bytes and their digest, full selected source
fingerprints, selection provenance and comparison basis. Later refreshes cannot
replace them. Freshness is checked independently of the current file page;
changed or unavailable sources are labelled. Historical base/commit attachments
retain that comparison basis. Frozen historical excerpts remain evidence of the
old snapshot rather than a claim about the latest checkout.

There are at most four attachments, each bounded to 6 KB including metadata. Their
serialized source envelopes enter the author request as **untrusted evidence**,
counting against the ordinary 8,000-character/256-line message boundary, pending
text, context, provider and storage limits. Rejection preserves the draft and
attachments for editing and retry. Admission retains the same provenance in JSON
and SQLite sessions, completed messages and message events. Resuming does not
resubmit a queued request automatically. Arbitrary prompts still require a
matching recording in the current conversation preview.

## Findings and explicit follow-ups

F12 or `/diff findings` projects findings from retained critic/judge reports,
including older SQLite review artifacts. Findings rank by impact and show their
stable ID, review-message position, category, critic attribution, judge disposition
and rationale, cited evidence, proposed correction and correction-request links.
The full report remains in the private session and existing history artifact view.

`/diff finding REVIEW_POSITION:FINDING_ID` opens the corresponding historical
source. Navigation requires an exact literal path and line/range plus a cited
quote present at those coordinates in that frozen diff. Ambiguous, absent or
unmapped evidence stays labelled and never receives guessed coordinates. Current
source revalidation determines staleness. Historical findings remain visible after
renames, deletions, corrections and disappearance from the live diff.

Use `/diff feedback KEY TEXT` to submit line-specific feedback with the finding's
frozen source and identity. `/diff fix KEY` explicitly submits a creator follow-up
request for the existing plan/test, bounded correction and verification workflow.
Both revalidate the review scope before admission and reject stale or unmapped
targets. Merely navigating never authorizes a write. A rejected follow-up keeps
the command and source attachment; retry does not duplicate the attachment.

Correction requests retain their finding and review-position links through resume.
They use the existing task policy, budgets and review counters. An author response
or a disappearing diff line never marks a finding resolved: corrected-revision
verification and independent review remain required. This viewer does not enable
live reviews, write tools or publication. Those require their existing controller,
containment and provider gates.

## Plain and JSON controls

The same frozen snapshots, source coordinates, attachment contracts and finding
identities are available without terminal layout:

```text
/diff
/diff refresh
/diff page 8
/diff lines src/example.py 0
/diff attach src/example.py 6 8
/diff remove 1
/diff findings
/diff finding REVIEW_POSITION:FINDING_ID
/diff feedback REVIEW_POSITION:FINDING_ID Check this condition
/diff fix REVIEW_POSITION:FINDING_ID
```

Page and expansion offsets are zero-based. Attachment row numbers are one-based
rows in the frozen patch, including its metadata rows; `/diff lines` prints those
row numbers and old/new source coordinates. Quote literal paths containing spaces.
Wait for an outstanding diff command to finish before issuing another; stop/quit
and ordinary conversation remain responsive during reads. EOF finishes an issued
read, while explicit quit cancels publication. Plain output escapes terminal
controls; JSON retains exact source bytes inside escaped strings. Pasted slash
commands and explicitly literal submissions remain ordinary message text.

The implementation is locally exercised on macOS, including a real PTY at 120
and 80 columns. This is not Linux/Windows-hosted WSL2 qualification, managed-worktree
support or proof of the gated live correction/review workflows.

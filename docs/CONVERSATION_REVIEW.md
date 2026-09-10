# Recorded review inside a conversation

An explicit `/review` or `Review this change.` now runs the existing recorded
critic/judge workflow and returns its result to the conversation. Ordinary chat
does not automatically invoke a panel. This remains a recorded-provider preview;
it does not inspect a repository, generate live reviews or make changes.

## Try the round-trip

Use distinct, new output files and a private storage directory:

```sh
mos conversation-review-demo --output /tmp/mos-review-chat.json --review-output /tmp/mos-review-packet.json
mos chat --cassette /tmp/mos-review-chat.json --review-packet /tmp/mos-review-packet.json --storage /tmp/mos-review-sessions
```

Enter these messages, waiting for each result:

```text
Remember that the fixture boundary is ten.
/review
What should be fixed?
```

The fixture review returns `revise` for a change that excludes quantity ten from
the required discount. The follow-up answers “Restore quantity >= 10.” The plain
phrase `Review this change.` creates the same canonical entry as `/review`;
matching ignores capitalization and a trailing period. General natural-language
intent routing remains future work.

You can quit after the review and use `mos resume <session-id>` or `mos resume
--last` with the same chat cassette and storage to ask the follow-up. The completed
review and input packet are retained in the private snapshot. Resume does not need
the original review file. `--review-packet` on resume configures new reviews;
already queued reviews retain their previously selected packet.

## Explicit inputs and isolated requests

`--review-packet` selects JSON containing `brief`, `cassette` and optional `policy`,
using the existing recorded review contracts. The specification, diff and
constraints are explicit user inputs. The brief hash must match the cassette.
The packet is validated once at startup; changing the source file during that
invocation does not change the target. Review without a configured packet reports
the unavailable capability.

The review runner receives only this packet. Critics receive its brief and their
assigned persona, and their recordings must match those exact request hashes.
They receive neither the conversation nor peer findings automatically. The judge
receives the brief and deduplicated findings through the existing identity-free
request. These schemas enforce structural separation; the user remains responsible
for the contents of an explicitly supplied brief. Fixture provider labels and
separate requests do not establish real model independence or review quality.

The existing policy controls quorum, citation validation, deduplication and the
verdict. A completed review may say `accept`, `revise` or `reject`; completion
describes the workflow, not code acceptance. Infrastructure failure is retained
as a failed review and pauses queued execution.

## Context, evidence and limits

The chat receives a labelled summary with the verdict, required-change/finding
counts, rationale, and up to five upheld findings with IDs, evidence excerpts and
suggested fixes. Excerpts are capped. The complete report is retained in
`review_result` and included in JSON lifecycle events on completion or explicit
resume. The summary identifies omitted detail. Subsequent model requests receive
the summary, not the complete packet/report; recorded replies still require exact
request hashes.

Human and NDJSON output share the controller. Review is one queued entry, shares
the 16-entry session cap, and leaves the chat cassette position unchanged. A packet
is limited to 128 KB and a result to 256 KB. The existing 2 MB aggregate snapshot
limit applies. Policy timeouts may be at most ten seconds per critic/judge call,
with a 25-second outer deadline. Existing roster, request-size and finding limits
remain in effect.

The running state is saved before critics execute. Ctrl-C and `/stop` cancel the
active review children and retain the cancelled entry. `/quit` and crash recovery
preserve the session; interrupted reviews are not retried on resume. Queued work
still needs explicit continuation. Failed, cancelled and interrupted reviews are
excluded from later model context. Unexpected reviewer diagnostics become a fixed
local error. A save failure prevents publication of a completed conversation
result and requires reopening the durable state before more work.

Review data uses the existing private snapshot, ownership/workspace checks, digest
validation and deletion controls. No separate review directory, index or remote
copy is created. Deleting the session removes its retained review data; original
user-supplied input files remain under separate user control. Digests detect
corruption, not hostile rewriting by a process running as the owner. Restored
results are bound to their brief and displayed summary; resume does not rerun the
critic/judge pipeline or independently authenticate a provider.

## Verification

Tests cover request isolation, both review triggers, absence of automatic panels,
contextual follow-ups, child cancellation, interrupted recovery, policy failures,
save failures, safe errors, byte/time limits, older snapshot compatibility and
bounded summaries. A subprocess test changes the packet file after startup,
completes the frozen review, resumes in another process without rereading that
packet, and deletes the retained session. The suite also runs against the installed
wheel. Validation on 2026-09-09: all 48 focused conversation tests passed, followed
by the full quality gate with 772 source tests (three optional integration skips),
88% branch-inclusive coverage, lint/format, strict typing, locked export, build
and 154 installed-wheel smoke tests. A real PTY exercised chat, review, contextual
follow-up, quit and durable evidence. All 150 local documentation link targets
resolved. No live provider calls were made.

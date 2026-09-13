# Guided reviews in terminal sessions

The terminal's existing `/review` command now accepts a frozen guidance-bearing
review packet. The plain terminal and full-screen UI use the same controller and
current-policy checks. This connects [guided recorded reviews](PROJECT_GUIDANCE_REVIEW.md)
to saved terminal sessions; execution still uses request-bound recorded fixtures.
It does not enable a live provider or grant tool/spend authority.

## Export and select a packet

First prepare and review the paired critic/judge brief described in
[guided recorded reviews](PROJECT_GUIDANCE_REVIEW.md). Export a terminal packet using
the exact reviewed prepared hash and a cassette for its derived brief:

```sh
umask 077
mos guidance-review packet -C /path/to/project \
  --prepared prepared.json --expected-prepared-sha256 PREPARED_HASH \
  --cassette /path/to/guided-cassette.json \
  --policy /path/to/private/policy.json --expected-policy-sha256 POLICY_HASH \
  --json > review-packet.json
mos -C /path/to/project --review-packet review-packet.json \
  --review-guidance-policy /path/to/private/policy.json \
  --expected-review-policy-sha256 POLICY_HASH
```

Use `/review` or `Review this change.` in the terminal. `--plain` selects the line
interface; `--tui` selects the full-screen interface. JSON output remains available.
If a custom guidance root was used, select it with `--guidance-storage` during packet
export and `--review-guidance-storage` at terminal launch. Policy and expected hash
must be supplied together; the policy file is never inferred from packet contents.

Packet export returns packet JSON directly, suitable for the explicit redirection
above, and creates no saved run. The complete terminal packet remains bounded to
128,000 canonical bytes, including guidance provenance, brief, cassette and policy.
A prepared review that fits its separate 512 KiB cap can still be too large for this
terminal boundary. Overflow rejects without truncation. Existing request, result,
pending-input and whole-session limits remain in force.

## Queue, execute and resume

Guided review admission checks exact owner/workspace, frozen projection, current
assessment and the selected policy before queueing, immediately before starting,
and around recorded review execution. Stale queued work remains queued and paused
without starting an attempt. A change during execution marks the review failed and
discards the result. Locks never span asynchronous execution, and before/after checks
cannot prove uninterrupted validity between them.

Resume opens historical state without reactivating it. A queued guided review needs
an explicit current `--review-guidance-policy` and `--expected-review-policy-sha256`
for that launch before `/continue` can run it. Stored packet hashes and successful
historical results do not provide current permission. A directory switch clears
the selected review packet and policy/hash so they cannot silently follow another
project. Git-root discovery and project-memory mappings do not select guidance.

The full prepared guidance remains inside the review packet stored with the session.
Snapshot and SQLite storage preserve it; SQLite's explicit artifact inspection can
show it after original inputs or policy files are deleted. Those reads do not reopen
saved policy paths or perform current admission. Policy file paths, raw policy prose,
chat memory and creator transcripts are not appended to the review payload.

Review results return to the normal conversation flow without consuming a chat
cassette exchange. Guidance-bearing packet schema 2 requires exact matching prepared
guidance; schema 1 keeps its existing canonical bytes and rejects attached guidance.
The session schema and existing artifact fields stay compatible. A small shared
terminal-text module removes the former import dependency between directory identity
and session-picker loading without changing label escaping.

Rollback leaves all saved data intact, but older readers cannot load schema-2 review
packets. Keep the upgraded reader when retaining guided review sessions. Live provider
selection, transfer/spend authorization and live dispatch remain separate work.

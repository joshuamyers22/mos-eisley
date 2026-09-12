# Guidance-bearing recorded reviews

`mos guidance-review prepare|run` connects [current role admission](PROJECT_GUIDANCE_ROLE_ADMISSION.md)
to the existing recorded review pipeline and replay artifacts. Both critic and judge
receive the same frozen rules and rubric through an explicit `Brief.constraints`
block. The original specification, diff and constraints remain retained separately.

This is recorded fixture execution. It sends no provider requests, executes no tools,
and does not establish live model quality or grant runtime authorization. Live
terminal/provider integration remains separate work.

## Prepare the exact brief

Freeze one `critic` and one `judge` packet using [role guidance](PROJECT_GUIDANCE_ROLE_CONTEXT.md).
For this initial integration their scope, rule order/content, omissions, assessment
and policy hashes must match exactly. Their role fields differ. Different critic/judge
subsets require later support; no silent merging or preference resolution occurs.

Create paired selection JSON with this shape, replacing all hashes and scope:

```json
{
  "critic": {
    "snapshot_sha256": "CRITIC_SNAPSHOT_HASH",
    "context_sha256": "CRITIC_CONTEXT_HASH",
    "role": "critic",
    "scope": "Implement batch execution"
  },
  "judge": {
    "snapshot_sha256": "JUDGE_SNAPSHOT_HASH",
    "context_sha256": "JUDGE_CONTEXT_HASH",
    "role": "judge",
    "scope": "Implement batch execution"
  }
}
```

```sh
umask 077
mos guidance-review prepare -C /path/to/project \
  --brief /path/to/source-brief.json --selection /path/to/paired-selection.json \
  --policy /path/to/private/policy.json --expected-policy-sha256 POLICY_HASH \
  --json > preview.json
```

Review `prepared.brief` and the retained provenance. Save only the `prepared` object
as `prepared.json`, and retain `prepared_sha256`. Preparation writes no stored state;
the shell redirection above creates the explicit preview file. Output includes the
selected source brief and guidance, so keep it private. Surrounding requirement-source
text, policy prose and creator transcripts are never fetched or appended.

The prepared hash covers canonical JSON, so formatting the saved object does not
change its identity. Pair selection is bounded to 16 KiB. The complete prepared record,
including original and derived brief, is bounded to 512 KiB. The existing 32,000-character
constraints limit can reject a role packet that fit the standalone 64 KiB context cap.
Limits reject rather than truncate; full critic/judge request byte budgets still apply.

## Run and replay

The cassette must match the **derived** brief ID and exact critic/judge request hashes.
A cassette for the original brief cannot be reused unchanged. Fixture preparation
must explicitly use the reviewed derived brief; this command does not rewrite responses.

```sh
mos guidance-review run -C /path/to/project \
  --prepared prepared.json --expected-prepared-sha256 PREPARED_HASH \
  --cassette /path/to/guided-cassette.json --output /path/to/private/runs \
  --policy /path/to/private/policy.json --expected-policy-sha256 POLICY_HASH --json
mos replay /path/to/private/runs/RUN_ID
```

Run verifies the prepared hash, owner/project identity, both current snapshots and
selected policy before recorded execution and again afterward before saving. Changes
reject and require new review. No guidance lock is held across asynchronous execution.
The paired preparation API intentionally composes two shared read guards only during
short synchronous projection; it never upgrades them to write locks.

A completed run contains hashed `guidance-review.json` alongside the existing brief,
cassette, policy, result and events. Schema 3 requires guidance; schema 4 requires both
guidance and skill provenance when a Python caller supplies both. Schemas 1 and 2 keep
their prior artifact sets. Replay verifies exact deterministic brief projection and
artifact identities without reading current guidance, policy or original source files.
Historical replay does not claim that guidance is still current, nor does it authenticate
against a same-user rewrite of an entire run bundle.

Exit codes follow recorded review: 0 accept, 1 revise/reject, 2 infrastructure/input
failure. This command returns the complete run path directly. Run storage remains
private and uses its completion manifest last. A persistence failure can leave a
partial directory; it is not replayable without the manifest. External same-user
filesystem edits remain outside the cooperative lock boundary; checks cannot undo
caller side effects or prove uninterrupted policy validity between checks.

Reverting the command leaves historical artifacts intact, but older readers cannot
read schema-3/4 runs. Keep the upgraded replay reader when retaining these runs.

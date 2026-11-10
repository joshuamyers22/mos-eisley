# rc.17 signed Intel qualification continuation

Owner: Joshua Myers. Operator: Codex. Publication remains separate.

The protected release run [42685881830](https://github.com/joshuamyers22/mos-eisley/actions/runs/42685881830)
prepared and signed frozen source `e6b1d75cc4140b7fb31c4a7a36fcdaf931c8f481`.
Its three complete signed installation/offline/upgrade jobs and all four signed
replay/privacy jobs passed. Intel job `129463949538` was cancelled during rc.12:
GitHub's retained annotation says "The job has exceeded the maximum execution
time of 1h15m0s". The original run remains cancelled and publisher skipped.

Original Intel artifact `13718471924` retained ten reports: signed installation,
both-store installed offline checks, and eight actual predecessor upgrades through
rc.11, including rc.7 cross-epoch downgrade refusal. The other signed hosts retain
49 reports and the four replay jobs retain four reports. These are partial release
evidence, not a completed four-target qualification. Earlier local gate failures
remain failures as recorded in the replay-owner work note.

Objective: complete exactly seven missing Intel reports against the original
signed artifacts. Three 40-minute jobs cover (rc.12, rc.13), (rc.14, rc.15), and
(rc.16, offline native progress, generated Homebrew formula). Native startup and
per-command qualification deadlines remain unchanged. There is no runtime change,
retag, signing retry, original-job rerun, provider call or publication permission.

Selected guidance: `AGENTS.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`,
`docs/PYTHON_ENGINEERING_GUIDE.md`, and the verification-loop, threat-model and
work-note templates. Risk: material release-evidence admission. Resource ceiling:
one controller implementation plus one correction pass, three Intel jobs of at
most 40 minutes each, existing CI gates, and a three-hour completion window.
Stop for a native assertion failure, source/artifact mismatch, owner cancellation,
or evidence-admission failure; preserve failed receipts without automatic retries.

Blocking rubric:

- Exact original run, attempt, source, workflow, successful preparation, three
  signed host jobs and four replay jobs; original Intel timeout and skipped
  publisher are required. Offline mutation tests must refuse substitutions,
  missing/duplicate jobs, manual cancellation and publisher execution.
- An explicit frozen checkout supplies all runtime and existing qualification
  scripts and locked dependencies. The new controller is checked out separately.
  All retained software checksums, enrolled metadata signature, metadata SHA-256
  and Intel archive SHA-256 must pass before execution.
- Actual published predecessors retain the immutable release ID, source and
  signed metadata admission from the frozen workflow; no synthetic predecessor.
- Seven new reports must pass original assertions and bind the original candidate.
  Continuation receipts bind controller source, group, original run/attempt and
  each report hash. Existing reports remain byte-for-byte in original custody.
- Final review must account for all 70 expected reports and 52 predecessor
  journeys, preserving the cancelled original job and provenance of continuation.
  No fresh live-qualification request is prepared until that review passes.

Threat model: substituted run/source/artifact, broadened qualification, fabricated
prior success, timeout laundering and accidental publication. Controls are fixed
run/job identities and timeout annotation admission, immutable signed software
pins, separate controller/frozen checkouts, read-only Actions/contents/checks
permissions, no environments or signing secrets, explicit seven-report scope and
retained original failure. A passing controller check is not independent human
release approval. Owner evidence review and any publication authorization remain
separate. These engineering fixtures make no prospective evaluation claim.

Initial offline evidence: six adversarial admission tests pass; focused strict
Pyright passes. Complete CI and native continuation outcomes remain pending.

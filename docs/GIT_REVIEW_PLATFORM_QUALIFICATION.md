# Native Git review qualification (§31.7)

This record concerns the explicit Git review reader and its shared conversation
consumers on native Linux and Windows-hosted WSL2. It does not qualify a release,
new provider target, containment, real credential store, native Windows, the
conversation diff panel or the broader §27.1 WSL2 deployment contract.

## Reproduce the exact candidate

The [native workflow](../.github/workflows/git-review-platforms.yml) uses ordinary
Ubuntu 24.04 and Windows Server 2025 GitHub-hosted runners. The Windows job installs
Ubuntu-24.04, observes Windows version/build and actual `wsl --version` and
`wsl --list --verbose`, and requires the selected distro to report version 2.
Linux boot/kernel observations alone are insufficient Windows-host provenance.

A non-root Linux user runs the candidate, environments and temporary fixtures on
ext4. A Windows-created Git bundle is copied into Linux, hash-checked and cloned
there; Linux Git never exempts Windows-owned repository metadata from ownership
checks. Bootstrap Bash text is normalized to LF. Explicit `--exec` transport must
preserve a literal argument containing backslashes, spaces and quotes.
The Linux uv bootstrap is pinned to version 0.13.4 and the official archive digest.
No host credential files, environment dumps or real provider calls are needed.

Inside a clean exact reviewed Linux checkout with frozen development dependencies:

```sh
uv run --frozen python tools/qualify_git_review_platform.py qualify \
  --target linux --commit FULL_CANDIDATE_SHA \
  --output dist/qualification/linux.json
```

Use `--target wsl2 --host-evidence PATH` only with the separately collected matching
Windows host observations. This CLI trusts its operator-selected host artifact;
the recorded workflow/job provenance establishes where those observations ran.
There is no override for WSL1, root execution, container substitution or non-ext4
paths. See the [general WSL2 runbook](WSL2_QUALIFICATION.md) for broader deployment
checks, including human Windows Terminal behavior, containment and keyring support.

## Required evidence

Each target must pass `make check -j1`, including source tests, lint/format, typing,
coverage, dependency export, build and the full installed-wheel smoke suite.
The wheel must contain exactly the source Python module set and matching bytes.
The report retains the exact candidate, wheel SHA-256, Python/Git/uv/kernel/UID,
filesystem observations, full-suite counts/skips/durations and focused results.
It does not confer execution, production or release approval.

The following focused modules then run from source and an independent wheel
installation outside the checkout, with `-I`, explicit test fixtures, hash-pinned
runtime dependencies and a checked installed-package location:

- `test_git_review`, `test_git_review_ranges`, `test_git_review_worktrees`:
  all selectors, source/metadata identities, unsafe redirects/links/permissions,
  stale replacement, helper suppression, real CodingVCS staging, unchanged creator
  and child checkouts/indexes, and TUI/plain/JSON parity.
- `test_conversation_git_review`, `test_scoped_live_review`:
  source-bound previews, dispatch/publication revalidation, exact prepared source,
  retained JSON/SQLite scopes, queued/resumed freshness and read-only authority.
- `test_conversation_live_review`, `test_conversation_review`,
  `test_conversation_recovery`: existing policy/quorum, budgets, cancellation,
  one-use boundaries and protection against replaying uncertain effects.

All focused cases must pass without skips; source and installed counts must agree.
Platform skips in the broader suite are recorded explicitly. Missing/skipped
required review evidence is a failure, not an inferred pass. Structured artifacts
exclude unrestricted test logs, credentials and model/conversation payloads.

## Exact native results

[Run 39881254556](https://github.com/joshuamyers22/mos-eisley/actions/runs/39881254556)
passed for candidate `8cef1b42d7b739772c5362b9206d9466e0a43199` on native
Linux and actual Windows-hosted WSL2. Each target passed 116 focused source
and 116 independent installed-wheel cases without skips, plus the full
3,853-test source and 2,831-test wheel gates (17/13 platform skips).
Candidate, Windows host provenance and identical wheel identities were checked
against the structured artifacts on 2026-10-23. The
[work note](GIT_REVIEW_PLATFORM_QUALIFICATION_WORK_NOTE.md) retains exact identities,
failed attempts and scope limits. Broader platform/release support remains gated.

## Integrated candidates, 2026-10-25

The frozen rc.8 source `eadb415d31afd89b142e3229a8ccca72aca835ee` passed
[run 40153393500](https://github.com/joshuamyers22/mos-eisley/actions/runs/40153393500)
on Linux and actual Windows-hosted WSL2. Each target passed 3,875 source and
2,851 installed-wheel tests (17/13 platform skips), followed by 116 source and
116 installed focused cases with zero failures/errors/skips. Both 414-file wheels
match SHA-256 `9161df55226638717de1a9b96ea8819f8158df1ff263b4cea3d3c827db7609e7`.
Windows host, distro version 2, candidate, run and bundle identities were checked.

Current-main integration passed separately at tested merge `a5dab66` in
[run 40153431249](https://github.com/joshuamyers22/mos-eisley/actions/runs/40153431249).
Its 3,876 source / 2,863 wheel tests and 116+116 focused cases passed on both
targets, with 17/13 broader-suite skips and zero focused skips. Its 414-file wheel
hash is `d401f74ec226699769b6539946cbf52ea786145b2a4171369999f34ac6c66009`;
the tested merge tree equals final PR #334 head. These candidates use different
dependency sets; their artifacts and results are kept distinct.

The failed earlier rc.8 WSL2 run and permission-fixture correction remain in the
[preview record](RC8_REVIEW_PREVIEW_WORK_NOTE.md). The earlier subscription return
did not recur; its cause remains unknown. This closes exact integrated §31.7
qualification while retaining the broader platform and release limits above.

# Integrated and superseded branch history

This publication batch preserves older local branch ancestry without replacing
current main files. The merge uses the `ours` strategy for the listed historical
branches; before this record was added, its tree was byte-for-byte identical to
main `5a6be4e`. New feature and documentation proposals remain separate PRs.

| Historical branch | Disposition and evidence |
|---|---|
| `feat/analysis-parquet-cases` | MCP data work and analytical tests were already integrated through [PR #108](https://github.com/joshuamyers22/mos-eisley/pull/108) and [PR #117](https://github.com/joshuamyers22/mos-eisley/pull/117). Nine later analytical/MCP commits also have equivalent patches in main. |
| `feat/diff-attachment-authority` | The patch is already present in main, confirmed by `git cherry`. |
| `feat/diff-coalescing-worker` | The patch is already present in main, confirmed by `git cherry`. |
| `feat/review-campaign-sequencing` | The patch is already present in main, confirmed by `git cherry`. |
| `integrate/g0-main` | Only an old merge commit remains outside main; no new file changes. |
| `integrate/dependency-prs` | Only three old merge commits remain; the dependency changes are already integrated and later updated. |
| `fix/dependency-pyright-210` | Its Pyright 1.1.413 update is superseded by main's pinned 1.1.414. |
| `codex/pr-228` | Historical requirements-only Pydantic-core update; current main's coupled lock/export is retained. |
| `dependabot/uv/pydantic-core-2.48.0` | Closed dependency proposal ([PR #2](https://github.com/joshuamyers22/mos-eisley/pull/2)); current main's coupled lock/export is retained. |

This record grants no runtime, review, release, provider or study authority.
Validation compares the pre-documentation tree with main and checks the final diff
contains only this record. Reverting this merge removes its history bookkeeping;
current main implementation behavior is unaffected.

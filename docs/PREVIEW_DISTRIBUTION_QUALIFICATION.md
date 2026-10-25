# macOS/Linux preview distribution qualification

## Current published preview and next candidate

[rc.7](https://github.com/joshuamyers22/mos-eisley/releases/tag/v0.1.0-rc.7)
published on 2026-10-22 at `78bc17ce561df7e641a4dd0fc5aef56aa9deee58` through
[run 39849685337](https://github.com/joshuamyers22/mos-eisley/actions/runs/39849685337).
Its immutable inventory has 39 verified assets, four signed installations,
sixteen actual-predecessor upgrades and both generated macOS formula checks.
It retains its frozen subscription/interface runtime. npm/tap routes remain
separately versioned; this is not stable launch or general Windows/WSL2 support.

[rc.8 preparation](RC8_REVIEW_PREVIEW_WORK_NOTE.md) adds reviewed source changes
and the recovery storage-epoch fence. Its dependency-frozen source `eadb415` is
reachable from protected main and tagged `v0.1.0-rc.8`. Linux/actual WSL2 review
gates, all four tagged development distributions and both generated Homebrew
checks passed. Joshua approved signing preparation only in
[run 40217716964](https://github.com/joshuamyers22/mos-eisley/actions/runs/40217716964);
that run retains current enrolled-key and five-predecessor results. The candidate
remains unpublished and publication requires separate owner disposition. Epoch 2
refuses downgrade to rc.7; retain pre-upgrade private backups and an epoch-2 reader.
The records below retain their original artifact-specific scope.

## Polished standalone preview published: 2026-10-15

[Immutable rc.3](https://github.com/joshuamyers22/mos-eisley/releases/tag/v0.1.0-rc.3)
published at `b3f04b46fb2091e861bdf3fc5e900d933cf804b3` through
[tagged run 38778971142](https://github.com/joshuamyers22/mos-eisley/actions/runs/38778971142).
All four enrolled-key signed installation jobs, all eight upgrades from the real
rc.1/rc.2 predecessors, and both macOS generated-formula jobs passed. All 31 public
asset names, sizes and SHA256 digests match the qualified publication candidate.
The protected owner approved publication; release ID `414195118` is immutable.
See the [publication record](POLISHED_PREVIEW_RELEASE_WORK_NOTE.md) for source,
UI, saved-session, recovery and rollback evidence. Public npm/tap journeys below
remain rc.1 evidence; rc.3 standalone publication does not update those routes.

## Previous standalone release

[Immutable rc.2](https://github.com/joshuamyers22/mos-eisley/releases/tag/v0.1.0-rc.2)
published on 2026-10-15 at `ef6a66fc8911902cef7a91828b4b26e7d329020c` through
[tagged run 38676738368](https://github.com/joshuamyers22/mos-eisley/actions/runs/38676738368).
That release precedes the interface merge `b79d970`; its assets remain unchanged.
The historical rc.1 closeout below remains attributed to its original artifacts
and package-manager journeys.

## Published closeout: 2026-10-14

[Immutable preview `0.1.0-rc.1`](https://github.com/joshuamyers22/mos-eisley/releases/tag/v0.1.0-rc.1)
published at source `8cf38c83591e505a9c7b57f4d701b12cb80fc4c6`. The owner accepted
reviewed head `d58468f6b9fc614f5633e1a836ec904d9afbc155`, whose tree matches the
protected merge. [Delivery review #302](https://github.com/joshuamyers22/mos-eisley/pull/302)
retains the acceptance, initial failures and preview limits.

[Tagged run 38602522715](https://github.com/joshuamyers22/mos-eisley/actions/runs/38602522715)
passed 3,702 source tests (17 skips), 2,725 installed-package tests (13 skips),
85% coverage, audit/container checks, four enrolled-key frozen-bootstrap jobs and
both macOS signed generated-formula jobs. All 23 public assets matched the
qualified candidate; GitHub's immutable release attestation verified.

[OIDC staging run 38629443613](https://github.com/joshuamyers22/mos-eisley/actions/runs/38629443613)
passed after owner 2FA renewed the five stage-only bindings. All five packages
were inspected and published at `0.1.0-rc.1` under `preview`, natives before
launcher. Public tarballs matched the stages and 3,188 generated package members.
Old `0.1.0` stages were excluded. [Tap PR #1](https://github.com/joshuamyers22/homebrew-mos-eisley/pull/1)
admitted the unchanged formula through protection.

Actual public standalone, npm and Homebrew install/setup/uninstall passed on
macOS arm64. Standalone discovery/recovery passed; npm discovery reported current
after explicit preview opt-in. Public archive identity checks cover all four
targets. No paid calls or studies ran. WSL2, billing/native retries/general
reliability and independent encrypted publisher backup/restore retain their
disclosed limits. Subsequent standalone real-predecessor qualification is recorded
separately below; the original rc.1 artifacts and receipts remain unchanged.

## Objective, authority and scope

Joshua Myers requested completion of distribution/installation qualification and
publication, then postponed actual Windows-hosted WSL2 qualification and explicitly
selected a macOS/Linux preview. The candidate is `0.1.0-rc.1`, not the stable
`0.1.0` product launch. Standalone and npm targets are macOS/Linux arm64/x86_64;
the initial Homebrew preview route is macOS. WSL2 and native Windows remain
unsupported by this preview. No inference or study is needed for these gates.

Guidance: repository `AGENTS.md`, `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`,
`docs/ADVERSARIAL_REVIEW_PLAYBOOK.md` and `templates/THREAT_MODEL.md`. Preserve
user worktrees, credentials, saved sessions and immutable usage/spend history.
One coherent full local quality gate and exact-candidate CI precede publication;
a changed artifact or a failing gate requires affected verification. Stop on
signature, version, source, platform, state-preservation or publication mismatch.

## Subscription reconciliation

PRs [#291](https://github.com/joshuamyers22/mos-eisley/pull/291) and
[#292](https://github.com/joshuamyers22/mos-eisley/pull/292) merged through protection.
Merged source `1d4d090` has the reviewed tree
`b8fb55700876e39a2f97f399f5a5de7f2eaa8398`. Source and a fresh installed wheel each
passed 109 focused checks; all 401 runtime files matched wheel/source archives.
The exact owner-authorized synthetic provider-diverse qualification is complete.
Native retries, cancelled usage, billing, general critic quality and repeated-run
reliability remain unverified; subscription commands retain explicit authorization.

## Required candidate evidence

| Gate | Evidence and decision |
|---|---|
| Source and installed package | Combined `make check`, frozen runtime export, build, locked audit and protected exact-head CI; initial failures remain attributed. |
| Four native targets | `app-distribution.yml` runs actual standalone runtime, npm local packaging and macOS generated-formula installation; retained `qualification-*.json` binds archive/bootstrap/platform/source identities. |
| Independent runtime | Installed setup/help/chat/cold resume run with neither external Python nor Node on PATH and no provider credentials. |
| Recovery and refusal | Recorded context survives upgrade/rollback, actual interrupted activation and recovery; altered archives/runtimes/signatures reject; uninstall preserves user state and removes owned runtime/launcher. |
| Publisher authentication | The protected release preparation signs exact artifacts with the enrolled key. All four native jobs execute the unpatched frozen bootstrap against that signed metadata before public publication. |
| Formula | The actual generated preview formula is installed/tested/uninstalled with only its exact archive URL replaced by a local fixture. Signed-candidate macOS jobs repeat against enrolled metadata; actual public tap verification follows publication. |
| Immutable publication | A mainline semantic tag matching metadata; no artifact overwrites; GitHub prerelease, npm `preview` tag, separate Homebrew preview formula. |
| Accountable review | The prepared candidate, remaining risks and exact CI/artifact identities need owner disposition; the agent's technical review is not independent approval. |

The original tagged preview upgrade/rollback receipts used explicitly synthetic
`0.0.0` metadata on the same frozen code; those receipts establish transaction
mechanics. The later [published-predecessor qualification](PUBLISHED_PREDECESSOR_UPGRADE_WORK_NOTE.md)
and [delivery review #305](https://github.com/joshuamyers22/mos-eisley/pull/305)
bind the untouched published rc.1 archives and enrolled-key metadata to the
unpublished rc.2 native candidate. They cover standalone JSON/SQLite save/resume,
pre/post activation recovery, rollback after candidate-written state, tamper
refusal and both versions' uninstall on the four advertised native targets.
This evidence applies to that exact artifact pair; future runtime/dependency/schema
changes and package-manager upgrades require fresh qualification. The tagged release
workflow repeats the actual-predecessor journey against the exact signed tag
artifacts before publication. First-bootstrap
trust remains GitHub HTTPS plus inspected checksums; checksums are not publisher
signatures. Neither this qualification nor signed preparation metadata authorizes
publishing rc.2 or declaring stable v1 support.

## Publisher and public-service handoff

The existing protected `application-release` environment, enrolled public root,
encrypted signing secret and immutable tag rules are retained. Publication is split
into preparation, four signed-install qualification jobs and a gated publication
job. No private key enters Git or a retained artifact. Private encrypted backup
custody and restore remain an owner-operated responsibility from
`PUBLISHER_RELEASE_PREPARATION.md`; no unverified backup is claimed here.

npm stage-only trust and final owner 2FA approval remain distinct. Native packages
must be approved before the launcher, all at the identical preview version/tag.
An expired login/trust relationship must be renewed through the native npm browser
flow; no token-based fallback is introduced. The generated Homebrew formula is
admitted only once its exact public archive URLs exist.

The closeout above and linked delivery review record completed public checks.
The original requirements retained here remain the acceptance rubric for the
preview and do not establish stable v1 readiness.

# macOS/Linux preview distribution qualification

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

Upgrade/rollback uses the same code with explicitly synthetic `0.0.0` distribution
metadata. It proves transaction mechanics, not compatibility with a real prior
published release. The production-key bootstrap and untrusted-signature rejection
are distinct from ephemeral local fixture signing. First-bootstrap trust remains
GitHub HTTPS plus inspected checksums; checksums are not publisher signatures.

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

Public release/download/registry/tap checks and final exact source/artifact/CI links
will be recorded in the delivery PR and immutable GitHub prerelease. This preparation
record does not claim a published installer or full v1 production readiness.

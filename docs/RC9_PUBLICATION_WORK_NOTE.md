# rc.9 owner review, publication and public verification

- Status: closed; immutable standalone preview published and public checks passed.
- Accountable release owner: Joshua Myers.
- Execution and technical verification: Codex; no independent security-review claim.
- Date: 2026-10-26 UTC.
- Frozen source: `f94842a44b9fc5dcf42a7f5880a6683e4fdc0b23`.
- Tag: `v0.1.0-rc.9`; storage epoch 2; retained rc.8 dependency set.
- Release: [424828190](https://github.com/joshuamyers22/mos-eisley/releases/tag/v0.1.0-rc.9),
  published `2026-10-26T22:16:05Z`, immutable prerelease with 47 assets.
- Protected workflow: [40246538826](https://github.com/joshuamyers22/mos-eisley/actions/runs/40246538826), completed successfully.

## Objective, authority and completion evidence

The owner explicitly requested completion of owner review and publication of
rc.9 at `f94842a`, after receiving the exact-candidate qualification review.
That instruction supplies accountable publication authority beyond the agent's
technical self-review. It does not authorize provider inference, studies, stable
v1 launch, npm staging/publication or a public Homebrew tap update.

Accept the four-target macOS/Linux standalone preview with its recorded unpaid
acceptance scope and epoch-2 downgrade fence. Preserve the original rc.8 tag,
failed evidence, signing root, user state and main's separate SDK/HTTP migration.
Do not overwrite a published asset or retarget a tag. Any failed publication
response requires reading actual state before retrying; an immutable publication
is retained. Existing 20-minute publication and four-hour per-gate bounds apply;
public checks use zero provider calls and bounded network/process timeouts.

Guidance: repository AGENTS/CONTRIBUTING, bounded verification guide/loop,
[release readiness checklist](../checklists/RELEASE_READINESS.md),
[publisher operation](APPLICATION_INSTALLATION.md#publisher-operation-and-remaining-stable-gates),
work-note template and [the prepublication review](RC9_PREPUBLICATION_REVIEW.md).

## Review and protected publication

Fresh review verified the enrolled Ed25519 metadata signature and freshness,
source/version/epoch, all 47 qualified asset identities and all 30 native receipts.
Those receipts cover four signed installs, four both-store installed matrices,
twenty actual published-predecessor upgrade/refusal journeys and two generated
Homebrew formula journeys. The original source/wheel/audit/container and four
native platform gates remain attributed to the exact candidate and all passed.
No qualification artifact grants publication or inference authority by itself.

The remote annotated tag still resolved to the frozen source. Repository release
immutability was enabled. Only `publish` was waiting, all ten prerequisite jobs
had succeeded, and approval history contained preparation only. Local publication
preflight passed. Publication approval was submitted under the owner's explicit
instruction to the separate protected `application-release` gate; deployment
record `7323224531` identifies that publication approval.

The protected job created a draft, uploaded the qualified inventory, verified all
names/sizes/SHA256 digests, and finalized it. GitHub confirmed source `f94842a`,
prerelease classification, `draft=false` and `immutable=true`. The completed
workflow reports success. `gh release verify` also cryptographically verified
GitHub's immutable-release attestation; its annotated-tag object and all 47
asset digests match the qualified inventory. The signed metadata SHA256 remains
`692b694d2683809f9a8fccd4499f682247a3c17702c2891a20f334750fe5dc23`.

## Public delivery and installed consumer verification

All **47 assets were downloaded without authentication** from their public
release URLs and matched the qualified sizes and SHA256 digests. HTTPS redirects
were confined to GitHub and its release-asset host. The public metadata verified
against the unpatched enrolled root and exact source/version/epoch.

On **macOS 15.1 arm64**, the verified public `install.sh` fetched the native
bootstrap, signed metadata and archive online into private disposable roots.
Neither Python nor Node was on the child PATH; only required OS utilities and
Git were present. The actual installed native runtime passed:

- Exact version, help and credential-free setup with both provider-key flags false.
- Snapshot and SQLite committed exec, passive reopen without attempt/journal replay,
  contextual cold resume and exactly one admitted follow-up.
- Owned idle-terminal process-loss recovery with unchanged committed history.
- Real terminal/diff attachment, stale-source refusal with retained draft,
  excerpt removal, Unicode/multiline paste, resize and terminal-mode restoration.
- Uninstall removing the owned launcher while retaining identical session bytes
  for both stores and terminal fixtures.

All public bytes match the four-platform artifacts already qualified natively.
The postpublication installed-consumer replay is macOS arm64 evidence; it does
not claim a new public-install execution on the other three architectures.
No provider call or study ran. Existing full-v1, live effectiveness, operational,
general Windows/WSL2, Apple notarization/cask and publisher backup/restore gates
retain their separate scopes. npm and public-tap versions remain separately qualified.

## Attempts, evidence and exit

The first private asset-review driver invocation had a local import-path error;
its path was corrected before any downloads or acceptance claims. All 47 public
asset checks then passed. The first public shell installation inherited unsupported
`C.UTF-8` on macOS and stopped in the system Perl checksum utility, before the
native installer ran. `locale -a` confirmed `en_US.UTF-8`; the replay selected that
installed locale and passed all checks. No product, signature, state-preservation
or isolation assertion was changed or skipped, and published bytes were unchanged.
Disposable installation directories were removed after state-preserving uninstall.

| Private verification record | SHA256 |
|---|---|
| `owner-decision.json` | `bc27cdf9c5f4c3102b2f71d78cf324f6d5ad34e82054278041b5a51d816b9f4b` |
| `public-asset-review.json` | `0d93924fdbd832d2741e16dac7d764249422394794c3cfe34ff321fab6fa1cca` |
| `public-install-review.json` | `2042089f6cd025583279e13597d18b072a40eed66242909df9f423e620cfc726` |
| `publication-review.json` | `870a3c871f5ed1a5df5dad2512ac3c97ccf59a66abfb75bce1c68b9a8a0dc47e` |
| `attestation-review.json` | `d2c426704874aaea87e734204ca84fd9980291236f9d56e71d10c8190f09ea42` |

Stop reason: owner-authorized publication and requested public verification
achieved. No unresolved failure remains in this release scope. Promote the
published identity and verification facts to the installation guide, preview
qualification index and project memory. Retain private byte/receipt manifests;
keep private keys, credentials, raw transcripts and sampling artifacts out of Git.
Future runtime fixes require a new immutable version and fresh qualification.

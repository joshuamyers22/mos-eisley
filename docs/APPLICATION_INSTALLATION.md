# Application installation and updates

The latest published standalone preview is
[immutable `0.1.0-rc.2`](https://github.com/joshuamyers22/mos-eisley/releases/tag/v0.1.0-rc.2),
source `ef6a66fc8911902cef7a91828b4b26e7d329020c`, for macOS/Linux ARM/x86.
It predates the polished interface. The
[rc.3 preparation record](POLISHED_PREVIEW_RELEASE_WORK_NOTE.md) tracks that new
candidate and upgrades from both published previews; rc.3 is not published yet.

The initial [immutable `0.1.0-rc.1` preview](https://github.com/joshuamyers22/mos-eisley/releases/tag/v0.1.0-rc.1)
was published for macOS and Linux on arm64 and x86_64. Its standalone installers and all
five `@mos-eisley` npm packages are public; the
[official Homebrew tap](https://github.com/joshuamyers22/homebrew-mos-eisley) supplies
`mos-eisley-preview` for macOS. [Publisher acceptance and public verification](https://github.com/joshuamyers22/mos-eisley/pull/302)
bind the release to source `8cf38c83591e505a9c7b57f4d701b12cb80fc4c6`.
Python/uv development installation continues to work as documented in the README.

## Preview selection

The owner selected a macOS/Linux-only `0.1.0-rc.1` preview while postponing WSL2
qualification. The stable `0.1.0` platform contract remains unqualified. The
[preview qualification record](PREVIEW_DISTRIBUTION_QUALIFICATION.md) links the
exact source, native jobs, publisher acceptance and public installation evidence.
The tagged release passed four signed installation gates and both macOS formula
gates. Actual public standalone/npm/tap journeys passed on macOS arm64; all 23
release assets and all five registry tarballs matched the qualified candidate.

Download and inspect `install.sh` from the exact
`v0.1.0-rc.2` GitHub release, then run:

```sh
sh install.sh --channel preview --version 0.1.0-rc.2
```

npm requires Node 22 or later. The explicit preview package command is:

```sh
npm install --global @mos-eisley/mos-eisley@preview
```

The Homebrew preview route is qualified initially for macOS:

```sh
brew install joshuamyers22/mos-eisley/mos-eisley-preview
```

Standalone and npm packages cover both macOS/Linux architectures. The preview
formula and npm tag are distinct from stable; switching to a stable installation
is an explicit later choice. `mos setup`, `mos --version`, and recorded chat work
without provider credentials. Run `mos update preview` to explicitly select the
preview feed for an existing installation. A new preview bootstrap preserves that
selection automatically. Package-manager upgrades use their own commands.

## Standalone installation

Native builds contain the Python runtime and dependencies. The qualified preview
matrix is macOS and Linux, each on arm64 and x86_64. Native Windows is excluded;
Linux tests do not establish Windows-hosted WSL2 qualification.

Acquire the approved release's `install.sh`, matching
`mos-install-<platform>`, `release.json` and archive from the exact GitHub release.
Review the bootstrap source and published checksums before executing it. The
bootstrap itself relies on the selected HTTPS publisher; the application archive
also requires signed metadata verified against the public key embedded in the
installer. Checksums alone are not a publisher signature.

For offline installation, run the matching native bootstrap:

```sh
./mos-install-macos-aarch64 --metadata release.json \
  --archive mos-0.1.0-rc.1-macos-aarch64.tar.gz --version 0.1.0-rc.1 --channel preview
```

The default runtime root is `~/.local/share/mos-eisley-app`; the launcher is
`~/.local/bin/mos`. Add that bin directory to PATH if necessary. Installation
requires no provider credentials. Existing sessions, credentials and spending
records remain separate from the runtime root.

## First launch and account sign-in

Run `mos setup` for credential-free readiness checks. The owner selected an
existing provider account through browser sign-in. Install the official Codex or
Claude client using its provider documentation, then use:

```sh
mos auth login openai
mos auth status openai
mos auth login anthropic
mos auth status anthropic
```

The native client owns the browser flow and credential storage. Mos never asks
for the provider account password or copies its tokens. Login requires an
interactive owner terminal. Relative and current-project PATH entries are
excluded; owners still need to install and trust the selected client. Login runs
from the home directory, with native-client configuration still applicable.

An [experimental subscription text route](SUBSCRIPTION_INFERENCE_WORK_NOTE.md)
is available through owner-installed Codex 0.161.0. `mos subscription status`
reads native login metadata without sending a prompt. `mos subscription ask --help`
shows explicit transfer/usage consent and fresh private-attempt requirements.
Only `gpt-6-sol` with `medium` effort is currently compatible. Native transport
retries may consume usage; local output/deadline limits are not billing caps.

[Experimental subscription sessions](SUBSCRIPTION_SESSIONS.md) now bind explicit
owner authorization through saved chat/resume and bounded creator/child/critic/judge
coding. The exact synthetic OpenAI/Anthropic qualification passed and PRs #291/#292
merged; native retry exposure, uncertain cancelled usage and billing remain
unverified. Login alone supplies no inference or coding authority.
Existing API routes retain their own authorization and spending controls.
Recorded conversation remains available without credentials. Setup and login
supply no inference prompt or paid Mos request.

Provider references: [Codex authentication](https://learn.chatgpt.com/docs/auth)
and [Claude CLI authentication](https://code.claude.com/docs/en/cli-reference).

## Updates and recovery

```sh
mos update check
mos update --version 0.1.1
mos update later
mos update skip --version 0.1.1
mos update disable
mos update enable
mos update preview
mos update stable
```

Versions above are examples, not available releases. Interactive standalone
updates ask for confirmation; scripts require `--yes`. Discovery is bounded and
cached; offline failure reports inability to check rather than claiming current.
Only interactive installed sessions show background notices. `/update` checks
without stopping conversation; `/update now` gives explicit close, update and
resume instructions. It never automatically restarts or replays paid work.

The installer stages and verifies the binary before switching the current
pointer. Active clients block replacement. A transaction journal and retained
previous version support interrupted-operation recovery and compatible rollback:

```sh
mos update recover --yes
mos update rollback --yes
mos resume --last
mos update uninstall --yes
```

Rollback verifies retained files and storage compatibility. Uninstall removes
owned runtime files and launcher only, preserving user state. Source/developer
installations are not silently taken over. npm/Homebrew installations receive
their own package-manager commands; automatic manager upgrades and rollback are
not implemented by this preview. Select discovery with `mos update preview`;
the default stable feed cannot discover this prerelease.

Root administrators may set `/etc/mos-eisley/update-policy.json` to
`{"schema":1,"mode":"disabled"}` or `{"schema":1,"mode":"managed"}`. This must
be a root-owned regular file, not writable by group or others. It overrides user
policy. User-controlled policy never changes release origins or the trusted key.

## Publisher operation and remaining stable gates

The enrolled public key is in `app_release_key.py`. Its dedicated private key is
outside Git in the owner's private configuration directory. It is not a provider
credential. Do not paste keys into chat, PRs, logs or workflow files.

1. Obtain accountable acceptance of the exact candidate and advertised support.
   Keep GitHub release immutability enabled and check it before approving the
   protected publication job. Its contents-only token cannot inspect the setting,
   which requires Administration permission.
2. Create a new mainline tag matching package metadata. The release workflow
   retains the full quality, signing and four-platform signed-installation gates.
   Publication automatically creates a draft, uploads qualified assets, verifies
   every uploaded name/size/SHA256 and only then publishes it. GitHub must confirm
   immutable publication. Upload or pre-publication verification failure leaves
   the draft unpublished. Matching partial drafts can resume; published releases
   and mismatched assets stop the job. Manual draft preparation is no longer
   required. A final response error may follow successful publication: inspect
   GitHub state before retrying, and preserve a published release.
3. Stage the identical version using `npm-publication.yml` and stage-only OIDC.
   Inspect stages and approve natives before launcher through owner 2FA. Preview
   uses `preview`, preserving `latest`. Renew an expired unvalidated binding
   through npm's browser flow; retain the stage-only publication boundary.
4. Admit the exact generated formula through the protected tap PR and verify
   public installation. Preserve its URLs/checksums, frozen-library rpaths and
   `libexec` cleaning exclusion.

The protected `application-release` environment requires owner approval, disallows
administrator bypass and restricts deployment to version tags. The enrolled key
remains in encrypted `MOS_RELEASE_SIGNING_KEY_BASE64` custody. Independently
retained encrypted backup/restore remains owner work. Never repair an executable
at an existing version: issue a new version and new signed metadata.

Stable `0.1.0` still needs actual Windows-hosted WSL2 qualification. The original
preview receipts used a synthetic predecessor. The separate
[real-predecessor qualification](PUBLISHED_PREDECESSOR_UPGRADE_WORK_NOTE.md) pins
the actual published `0.1.0-rc.1` and an unpublished `0.1.0-rc.2` candidate for
standalone upgrade, JSON/SQLite cold resume, interrupted activation recovery,
rollback after candidate writes and uninstall on all four macOS/Linux targets.
Its exact results and accountable acceptance are recorded in
[PR #305](https://github.com/joshuamyers22/mos-eisley/pull/305).
Tagged publication repeats this journey against the exact freshly signed tag
artifacts on all four targets before publishing; preparation results do not
substitute for that gate.
The rc.3 release preparation also requires a separate journey from immutable rc.2,
with distinct evidence and the same signature, state, recovery and rollback checks.
New runtime/schema changes and package-manager upgrades require their own
qualification. Subscription billing, native retry exposure, general reliability
and publisher backup/restore remain unverified. rc.2 is published; rc.3 publication
requires fresh exact-candidate qualification and owner disposition.

Official publisher guidance: [npm trusted publishers](https://docs.npmjs.com/trusted-publishers/),
[scoped public packages](https://docs.npmjs.com/creating-and-publishing-scoped-public-packages/)
and [Homebrew taps](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap).

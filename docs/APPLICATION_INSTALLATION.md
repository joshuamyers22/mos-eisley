# Application installation and updates

This candidate prepares distribution; it is not a published installer. The npm
scope is provisional, the Homebrew tap does not exist, and platform CI and
accountable release approval remain gates. Python/uv development installation
continues to work as documented in the README.

## Standalone installation

Native builds contain the Python runtime and dependencies. The proposed release
matrix is macOS and Linux, each on arm64 and x86_64. Native Windows is excluded;
Linux tests do not establish Windows-hosted WSL2 qualification.

After an approved release exists, acquire its `install.sh`, matching
`mos-install-<platform>`, `release.json` and archive from the exact GitHub release.
Review the bootstrap source and published checksums before executing it. The
bootstrap itself relies on the selected HTTPS publisher; the application archive
also requires signed metadata verified against the public key embedded in the
installer. Checksums alone are not a publisher signature.

For offline installation, run the matching native bootstrap:

```sh
./mos-install-macos-aarch64 --metadata release.json \
  --archive mos-0.1.0-macos-aarch64.tar.gz --version 0.1.0
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

**Subscription-backed Mos inference remains unavailable.** Login does not turn
the existing qualified API routes into subscription routes. A separate supported
adapter and qualification are needed before this account can power Mos coding.
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
not implemented by this candidate.

Root administrators may set `/etc/mos-eisley/update-policy.json` to
`{"schema":1,"mode":"disabled"}` or `{"schema":1,"mode":"managed"}`. This must
be a root-owned regular file, not writable by group or others. It overrides user
policy. User-controlled policy never changes release origins or the trusted key.

## Publisher preparation and remaining gates

The enrolled public key is in `app_release_key.py`. Its dedicated private key is
outside Git in the owner's private configuration directory. It is not a provider
credential. Do not paste keys into chat, PRs, logs or workflow files.

1. Complete accountable security/release review of the exact candidate, then
   pass repository checks and all native artifact jobs. Run the WSL2 journey on
   an actual Windows host before claiming that support.
2. Verify ownership of an npm account/scope. `@joshuamyers22` is a proposed name,
   not established ownership. Update the generator, launcher and update guidance
   together if the selected scope differs. Authenticate through npm's browser
   flow; configure trusted publication/provenance rather than putting a token in
   source. Publish native packages before the launcher package at the identical
   immutable version. Actual registry publication remains untested.
3. Create the proposed `joshuamyers22/homebrew-mos-eisley` tap, review the generated
   formula and commit that exact release's URLs/checksums. The formula preserves
   frozen-library rpaths and excludes libexec from cleaning. Local tap tests are
   not evidence that the public tap is available.
4. Configure and verify protection of the `application-release` environment,
   required reviewers and signing-key custody. The workflow references
   `MOS_RELEASE_SIGNING_KEY_BASE64`; no secret or protection was provisioned by
   this task. Enroll custody through the owner's approved secret-management path.
5. Publish an approved immutable tag whose version matches the package. The
   release workflow builds all four native bundles, signs their shared metadata,
   generates packages/formula, and attaches the direct-download assets. Stable
   and `-rc.N` preview releases use separate signed channels. Existing assets are
   not overwritten. Never repair an executable at an existing version: issue a
   new version and new metadata.

Official publisher guidance: [npm trusted publishers](https://docs.npmjs.com/trusted-publishers/),
[scoped public packages](https://docs.npmjs.com/creating-and-publishing-scoped-public-packages/)
and [Homebrew taps](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap).

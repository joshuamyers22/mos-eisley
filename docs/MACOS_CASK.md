# macOS project-tap cask

Status: **preparation only; not published or qualified for installation**.
The owner has no Developer ID. The current ad-hoc-signed preview fails Gatekeeper
and a normally quarantined copy is terminated by macOS. A third-party tap does
not remove that runtime requirement. The existing preview formula and standalone
rc.3 remain available under their existing qualification records.

## Package contract

One compressed read-only DMG per native architecture contains `Mos Eisley/mos`,
the complete PyInstaller runtime, license and `homebrew-cask` origin receipt.
Homebrew stages the whole image payload and links that binary into its prefix.
No system installer, root access, separate interpreter or graphical app is needed.
Initial package qualification targets macOS 15 and newer; newer macOS coverage
must be recorded before advertising it. Runtime-relative library paths and
framework links must remain intact. No uninstall hooks or `zap` remove user data.

The requested project-tap token is `mos-eisley`; its version/caveat explicitly
identifies preview releases. This is an owner-requested project-tap naming choice,
not stable-release or default-tap qualification. The intended command remains:

```sh
brew install --cask joshuamyers22/mos-eisley/mos-eisley
```

Do not advertise that command as available until the public-artifact gates below
pass. Existing immutable rc.3 cannot be modified to add this runtime behavior or
its new cask packages. Select a new version, mainline source and immutable release.

## Apple signing requirements

The owner must provision a valid **Developer ID Application** certificate with
its private key available to the signing runner, the expected Apple Team ID, and
an authenticated notarytool keychain profile. An Apple Development certificate,
ad-hoc signature or the Ed25519 application release key cannot replace Developer
ID/notarization. Keep certificate/key custody and notary credentials outside Git,
chat and workflow logs. No credentials are included in these package definitions.

Build on each native architecture from the same clean, tagged mainline version:

```sh
uv run --frozen python tools/build_standalone.py --output dist/cask-native \
  --codesign-identity "$MOS_APPLE_SIGNING_IDENTITY"
uv run --frozen python -m tools.build_macos_cask \
  --bundle dist/cask-native/bundle/mos \
  --identity "$MOS_APPLE_SIGNING_IDENTITY" --team-id "$MOS_APPLE_TEAM_ID" \
  --notary-profile "$MOS_APPLE_NOTARY_PROFILE"
```

PyInstaller signs the collected native code with hardened runtime. The cask
builder checks every Mach-O signature, expected team, secure timestamp and runtime
flag, rejects a debug task entitlement, signs the DMG, requires Apple notarization
`Accepted`, staples/validates the ticket and assesses the image with Gatekeeper.
No production receipt is written after a failed trust check. The two images must
be gathered without changing bytes, then the cask generator checks source,
version, architecture, team, size and hash and reassesses both real images:

```sh
uv run --frozen python -m tools.package_macos_cask --artifacts dist/cask \
  --team-id "$MOS_APPLE_TEAM_ID"
```

Receipts are coordination evidence, not authorization or a replacement for actual
Apple checks. Production generation pins version/source to its clean mainline tag
and pins the expected Apple team from owner configuration, not artifact claims.
Before public release, include both DMGs and qualification records
in the new version's complete protected immutable publication inventory. The
current standalone publisher does not yet admit these additional asset types;
that integration remains an explicit release gate, not an implied side effect
of the preparation workflow.

## Development review without Apple credentials

The separate `macOS cask preparation` workflow builds both native layouts with
`--development`, mounts them read-only and tests version/help/setup, recorded chat,
cold resume, cask ownership and no external Python/Node on PATH. Its generated
cask is **disabled**, uses local fixture URLs, and cannot be promoted by renaming
receipts or editing a JSON trust flag. Development layout success does not qualify
quarantined execution, Homebrew installation, upgrade, migration or publication.

## Installation, upgrades and migration gates

After trusted artifacts exist, use clean Apple Silicon and Intel Macs, default
Homebrew quarantine and fresh public downloads. Run cask style, normal audit and
explicit signing audit, then install by the exact full tap token. Verify the
selected `mos` resolves into that cask, version/help/setup, recorded chat/cold
resume, and `mos update` directing the user to the cask upgrade command.

Publish a second genuinely versioned candidate to exercise `brew upgrade --cask`
against its actual predecessor. Snapshot hashes of synthetic sessions, memory,
credential/configuration sentinels and spending records before each lifecycle
operation. Verify old saved conversations after upgrade and unchanged retained
state after `brew uninstall --cask`. Synthetic same-code relabeling is not real
upgrade qualification.

Migration is deliberate and separately tested for each existing installation:

1. Close active Mos sessions. Inspect `type -a mos` and current package ownership;
   record selected version and retained-state hashes. Do not use `--force` to take
   over a launcher, remove another manager's files or alter data storage.
2. For the preview formula, uninstall its exact formula through Homebrew. For uv
   or npm, remove only the owner-selected Mos package through that manager. For
   standalone, use its state-preserving `mos update uninstall --yes`. Retain a
   documented reinstall/rollback route for each old package.
3. Install the qualified cask, clear the shell command cache and confirm one
   selected launcher. Detect other earlier PATH entries; stop if an unrelated or
   unmanaged `mos` remains selected. Verify existing sessions and both storage
   backends, setup, update ownership and byte-identical private state.
4. Uninstall the cask and confirm it removes only its managed launcher/payload.
   Reinstall and cold-resume retained sessions. Also test a conflicting existing
   Homebrew-prefix binary is refused without overwriting it.

Publish only after exact-artifact owner review and a protected tap PR. Copy the
generated production cask without changing its immutable URLs or checksums; verify
the public command on both architectures after merge. Default-tap acceptance is
a later external decision, with current package eligibility reviewed separately.

See [work note](MACOS_CASK_WORK_NOTE.md),
[Cask Cookbook](https://docs.brew.sh/Cask-Cookbook),
[Acceptable Casks](https://docs.brew.sh/Acceptable-Casks),
[Apple notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
and [PyInstaller signing](https://pyinstaller.org/en/stable/feature-notes.html#macos-binary-code-signing).

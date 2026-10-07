#!/bin/sh
# Credential-free standalone bootstrap. Download/inspect/run is also supported.
set -eu
umask 077
case "$(uname -s)" in Darwin) mos_os=macos ;; Linux) mos_os=linux ;; *) echo 'Unsupported OS. Native Windows is excluded; WSL2 qualification is pending.' >&2; exit 2 ;; esac
case "$(uname -m)" in arm64|aarch64) mos_arch=aarch64 ;; x86_64|amd64) mos_arch=x86_64 ;; *) echo 'Unsupported architecture.' >&2; exit 2 ;; esac
command -v curl >/dev/null || { echo 'curl is required.' >&2; exit 2; }
mos_tag=latest
mos_channel=stable
mos_select() {
while [ "$#" -gt 0 ]; do
    case "$1" in
        --version) [ "$#" -gt 1 ] || exit 2; mos_tag="v$2"; shift ;;
        --channel) [ "$#" -gt 1 ] || exit 2; mos_channel="$2"; shift ;;
    esac
    shift
done
}
mos_select "$@"
case "$mos_channel" in stable) ;; preview) [ "$mos_tag" != latest ] || { echo 'Preview bootstrap requires --version.' >&2; exit 2; } ;; *) echo 'Invalid channel.' >&2; exit 2 ;; esac
case "$mos_tag" in *[!a-zA-Z0-9.-]*) echo 'Invalid release version.' >&2; exit 2 ;; esac
mos_tmp=$(mktemp -d "${TMPDIR:-/tmp}/mos-install.XXXXXXXX")
trap 'rm -rf "$mos_tmp"' EXIT HUP INT TERM
mos_name="mos-install-$mos_os-$mos_arch"
if [ "$mos_tag" = latest ]; then
    mos_base=https://github.com/joshuamyers22/mos-eisley/releases/latest/download
else
    mos_base="https://github.com/joshuamyers22/mos-eisley/releases/download/$mos_tag"
fi
mos_fetch() {
    mos_effective=$(curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --max-time 60 --max-filesize 134217728 --output "$2" --write-out '%{url_effective}' "$1")
    case "$mos_effective" in https://github.com/joshuamyers22/mos-eisley/releases/*|https://release-assets.githubusercontent.com/*) ;; *) echo 'Unexpected download origin.' >&2; exit 2 ;; esac
}
mos_fetch "$mos_base/$mos_name" "$mos_tmp/$mos_name"
mos_fetch "$mos_base/BOOTSTRAP_SHA256SUMS" "$mos_tmp/sums"
mos_expected=$(awk -v file="$mos_name" '$2 == file {print $1}' "$mos_tmp/sums")
[ "${#mos_expected}" -eq 64 ] || { echo 'Bootstrap checksum missing.' >&2; exit 2; }
if command -v sha256sum >/dev/null; then
    mos_actual=$(sha256sum "$mos_tmp/$mos_name" | awk '{print $1}')
else
    mos_actual=$(shasum -a 256 "$mos_tmp/$mos_name" | awk '{print $1}')
fi
[ "$mos_actual" = "$mos_expected" ] || { echo 'Bootstrap integrity check failed.' >&2; exit 2; }
chmod 700 "$mos_tmp/$mos_name"
# Preserve arguments without eval. They were parsed only to choose the bootstrap;
# the actual installer validates destination/channel/version and signed metadata.
"$mos_tmp/$mos_name" "$@"

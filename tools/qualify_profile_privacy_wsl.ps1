# Disposable GitHub Windows runner only. No production account or provider keys.
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$env:WSL_UTF8 = '1'
$distro = 'Ubuntu-24.04'
$evidence = Join-Path $env:GITHUB_WORKSPACE 'dist/qualification'
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
$bundleWindows = Join-Path $env:RUNNER_TEMP 'mos-privacy-source.bundle'
git bundle create $bundleWindows HEAD
$bundleDigest = (Get-FileHash -Algorithm SHA256 $bundleWindows).Hash.ToLowerInvariant()

function Invoke-WslBounded([string[]] $Arguments, [int] $Seconds = 600) {
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = 'wsl.exe'
    foreach ($argument in $Arguments) { $start.ArgumentList.Add($argument) }
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = [System.Diagnostics.Process]::Start($start)
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit($Seconds * 1000)) {
        $process.Kill($true)
        throw 'WSL startup/command exceeded its deadline'
    }
    $text = $stdout.GetAwaiter().GetResult().Replace("`0", '')
    $diagnostic = $stderr.GetAwaiter().GetResult().Replace("`0", '')
    if ($process.ExitCode -ne 0) { throw "WSL command failed: $text $diagnostic" }
    if ($diagnostic) { Write-Host $diagnostic }
    return $text.Trim()
}

$version = Invoke-WslBounded -Arguments @('--version') -Seconds 60
Invoke-WslBounded -Arguments @('--set-default-version', '2') -Seconds 60 | Write-Host
Invoke-WslBounded -Arguments @('--install', '--web-download', '--distribution', $distro, '--no-launch') | Write-Host
Invoke-WslBounded -Arguments @('--distribution', $distro, '--user', 'root', '--exec', 'true') | Write-Host
$listing = Invoke-WslBounded -Arguments @('--list', '--verbose') -Seconds 60
if ($listing -notmatch '(?m)^\s*\*?\s*Ubuntu-24\.04\s+\S+\s+2\s*$') {
    throw 'The actual selected Windows-hosted distribution must report version 2'
}
$hostOs = Get-CimInstance Win32_OperatingSystem
@{
    schema_version = 1
    host_os = 'Windows'
    windows_caption = $hostOs.Caption
    windows_version = $hostOs.Version
    windows_build = $hostOs.BuildNumber
    architecture = $hostOs.OSArchitecture
    wsl_version = $version
    distribution_listing = $listing
    distribution = $distro
    distribution_version = 2
    candidate_commit = $env:GITHUB_SHA
    source_bundle_sha256 = $bundleDigest
    workflow_run = $env:GITHUB_RUN_ID
    runner_image = $env:ImageVersion
} | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $evidence 'windows-host.json')

$bootstrap = @'
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git curl ca-certificates strace
curl --fail --location --retry 3 https://github.com/astral-sh/uv/releases/download/0.13.4/uv-x86_64-unknown-linux-gnu.tar.gz --output /tmp/mos-uv.tar.gz
echo '2b428396f12572d4429cf210ca234dd599a33b3af0958a4d5ed569d63e3f344f  /tmp/mos-uv.tar.gz' | sha256sum --check
tar -xzf /tmp/mos-uv.tar.gz -C /tmp
install -m 755 /tmp/uv-x86_64-unknown-linux-gnu/uv /usr/local/bin/uv
'@
$bootstrap = $bootstrap.Replace("`r", '')
Invoke-WslBounded -Arguments @('--distribution', $distro, '--user', 'root', '--exec', 'bash', '-c', $bootstrap) -Seconds 900 | Write-Host
$transportProbe = 'a\path with spaces"quote'
$transportResult = Invoke-WslBounded -Arguments @('--distribution', $distro, '--user', 'root', '--exec', 'bash', '-c', 'printf "%s" "$1"', '--', $transportProbe) -Seconds 60
if ($transportResult -cne $transportProbe) { throw 'WSL argument transport changed literal bytes' }
$source = Invoke-WslBounded -Arguments @('--distribution', $distro, '--user', 'root', '--exec', 'wslpath', '-u', $env:GITHUB_WORKSPACE) -Seconds 60
$bundleLinux = Invoke-WslBounded -Arguments @('--distribution', $distro, '--user', 'root', '--exec', 'wslpath', '-u', $bundleWindows) -Seconds 60
$run = @'
set -eu
export PATH=/usr/local/bin:/usr/bin:/bin
export UV_PYTHON_INSTALL_DIR=/opt/mos-privacy-python
umask 022
mkdir -p /tmp/mos-profile/assets /tmp/mos-profile/source /opt/mos-privacy-python
cp "$3" /tmp/mos-profile/source.bundle
printf '%s  /tmp/mos-profile/source.bundle\n' "$4" | sha256sum --check
git clone /tmp/mos-profile/source.bundle /tmp/mos-profile/source
cd /tmp/mos-profile/source
git checkout --detach "$2"
base=https://github.com/joshuamyers22/mos-eisley/releases/download/v0.1.0-rc.16
for asset in release.json BOOTSTRAP_SHA256SUMS requirements.runtime.txt mos_eisley-0.1.0rc16-py3-none-any.whl mos-0.1.0-rc.16-linux-x86_64.tar.gz mos-install-linux-x86_64; do
    curl --fail --location --max-time 180 "$base/$asset" --output "/tmp/mos-profile/assets/$asset"
done
uv venv --python 3.12 /tmp/mos-profile/venv
uv pip install --python /tmp/mos-profile/venv/bin/python --requirements /tmp/mos-profile/assets/requirements.runtime.txt /tmp/mos-profile/assets/mos_eisley-0.1.0rc16-py3-none-any.whl
cp tools/privacy_actor.py tools/privacy_gate.py tools/qualify_profile_privacy.py /tmp/mos-profile/
chmod -R a+rX /tmp/mos-profile /opt/mos-privacy-python
cp "$1/dist/qualification/windows-host.json" /tmp/mos-profile/windows-host.json
GITHUB_ACTIONS=true RUNNER_ENVIRONMENT=github-hosted GITHUB_RUN_ID="$5" /tmp/mos-profile/venv/bin/python /tmp/mos-profile/qualify_profile_privacy.py --assets /tmp/mos-profile/assets --actor /tmp/mos-profile/privacy_actor.py --python /tmp/mos-profile/venv/bin/python --commit "$2" --host-evidence /tmp/mos-profile/windows-host.json --output /tmp/mos-profile/wsl2.json
'@
$run = $run.Replace("`r", '')
$qualificationFailure = $null
try {
    Invoke-WslBounded -Arguments @('--distribution', $distro, '--user', 'root', '--exec', 'bash', '-c', $run, '--', $source, $env:GITHUB_SHA, $bundleLinux, $bundleDigest, $env:GITHUB_RUN_ID) -Seconds 4200 | Write-Host
} catch {
    $qualificationFailure = $_
}
Invoke-WslBounded -Arguments @('--distribution', $distro, '--user', 'root', '--exec', 'bash', '-c', 'if [ -f /tmp/mos-profile/wsl2.json ]; then cp /tmp/mos-profile/wsl2.json "$1/dist/qualification/wsl2.json"; fi', '--', $source) -Seconds 60 | Write-Host
if ($qualificationFailure) { throw $qualificationFailure }

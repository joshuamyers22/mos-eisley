# Disposable GitHub Windows runner only. No production account or provider keys.
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$env:WSL_UTF8 = '1'
$distro = 'Ubuntu-24.04'
$evidence = Join-Path $env:GITHUB_WORKSPACE 'dist/qualification'
New-Item -ItemType Directory -Force -Path $evidence | Out-Null

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
    workflow_run = $env:GITHUB_RUN_ID
    runner_image = $env:ImageVersion
} | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $evidence 'windows-host.json')

$bootstrap = @'
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git make curl ca-certificates tmux build-essential
useradd --create-home --shell /bin/bash mosqual
curl --fail --location --retry 3 https://github.com/astral-sh/uv/releases/download/0.13.4/uv-x86_64-unknown-linux-gnu.tar.gz --output /tmp/mos-uv.tar.gz
echo '2b428396f12572d4429cf210ca234dd599a33b3af0958a4d5ed569d63e3f344f  /tmp/mos-uv.tar.gz' | sha256sum --check
tar -xzf /tmp/mos-uv.tar.gz -C /tmp
install -m 755 /tmp/uv-x86_64-unknown-linux-gnu/uv /usr/local/bin/uv
'@
$bootstrap = $bootstrap.Replace("`r", '')
Invoke-WslBounded -Arguments @('--distribution', $distro, '--user', 'root', '--exec', 'bash', '-c', $bootstrap) -Seconds 900 | Write-Host
$transportProbe = 'a\path with spaces"quote'
$transportResult = Invoke-WslBounded -Arguments @('--distribution', $distro, '--user', 'mosqual', '--exec', 'bash', '-c', 'printf "%s" "$1"', '--', $transportProbe) -Seconds 60
if ($transportResult -cne $transportProbe) { throw 'WSL argument transport changed literal bytes' }
$source = Invoke-WslBounded -Arguments @('--distribution', $distro, '--user', 'mosqual', '--exec', 'wslpath', '-u', $env:GITHUB_WORKSPACE) -Seconds 60
$run = @'
set -eu
export PATH=/usr/local/bin:/usr/bin:/bin
umask 077
cd ~
git clone --no-local "$1" candidate
cd candidate
git checkout --detach "$2"
uv sync --frozen --dev
mkdir -p dist/qualification
cp "$1/dist/qualification/windows-host.json" dist/qualification/windows-host.json
MOS_REQUIRE_TMUX=1 uv run --frozen python tools/qualify_git_review_platform.py qualify --target wsl2 --commit "$2" --host-evidence dist/qualification/windows-host.json --output dist/qualification/wsl2.json
'@
$run = $run.Replace("`r", '')
# Use the same explicit argv transport checked above for the long quality run.
$qualificationFailure = $null
try {
    Invoke-WslBounded -Arguments @('--distribution', $distro, '--user', 'mosqual', '--exec', 'bash', '-c', $run, '--', $source, $env:GITHUB_SHA) -Seconds 7200 | Write-Host
} catch {
    $qualificationFailure = $_
}
# Only structured evidence crosses back; preserve a failed run's report as well.
Invoke-WslBounded -Arguments @('--distribution', $distro, '--user', 'mosqual', '--exec', 'bash', '-c', 'if [ -f ~/candidate/dist/qualification/wsl2.json ]; then cp ~/candidate/dist/qualification/wsl2.json "$1/dist/qualification/wsl2.json"; fi', '--', $source) -Seconds 60 | Write-Host
if ($qualificationFailure) { throw $qualificationFailure }

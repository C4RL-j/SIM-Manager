[CmdletBinding()]
param(
    [string]$Python = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'This portable build must run on Windows x64.'
}
if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
}
$Python = (Resolve-Path -LiteralPath $Python -ErrorAction Stop).Path
$Stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fffffff')
$PortableRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot 'dist\portable'))
$RunRoot = [IO.Path]::GetFullPath((Join-Path $PortableRoot $Stamp))
if (-not $RunRoot.StartsWith($PortableRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Build output is outside the repository portable directory.'
}
if (Test-Path -LiteralPath $RunRoot) {
    throw 'The fresh build directory already exists; rerun for a new timestamp.'
}
[void][IO.Directory]::CreateDirectory($RunRoot)
$Helper = Join-Path $ProjectRoot 'packaging\portable.py'
$PreviousBuildRoot = [Environment]::GetEnvironmentVariable('SIM_MANAGER_BUILD_ROOT', 'Process')
try {
    $env:SIM_MANAGER_BUILD_ROOT = $RunRoot
    & $Python $Helper prepare --run-root $RunRoot
    if ($LASTEXITCODE -ne 0) { throw 'Portable build preparation failed.' }
    & $Python -m PyInstaller --noconfirm --distpath (Join-Path $RunRoot 'app') --workpath (Join-Path $RunRoot 'build') (Join-Path $ProjectRoot 'packaging\SIMManager.spec')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed; the fresh build output was retained for review.' }
    & $Python $Helper finalize --run-root $RunRoot
    if ($LASTEXITCODE -ne 0) { throw 'Portable validation or archive creation failed.' }
}
finally {
    [Environment]::SetEnvironmentVariable('SIM_MANAGER_BUILD_ROOT', $PreviousBuildRoot, 'Process')
}

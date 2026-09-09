param(
    [ValidateSet("Internal", "Production")]
    [string] $Channel = "Internal",
    [string] $CertificateThumbprint = ""
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

if ($Channel -eq "Production" -and [string]::IsNullOrWhiteSpace($CertificateThumbprint)) {
    throw "CertificateThumbprint is required for Production builds."
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock] $Command
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Native command failed with exit code $($LASTEXITCODE): $Command"
    }
}

& "$PSScriptRoot\build_sidecar.ps1"

$tauriConfigPath = Join-Path $repo "apps\desktop-tauri\src-tauri\tauri.conf.json"
$tauriConfig = Get-Content -Raw $tauriConfigPath | ConvertFrom-Json
$installerName = "$($tauriConfig.productName)_$($tauriConfig.version)_x64-setup.exe"
$internalInstallerName = "$($tauriConfig.productName)_$($tauriConfig.version)_x64-internal-unsigned-setup.exe"
$nsisDir = Join-Path $repo "apps\desktop-tauri\src-tauri\target\release\bundle\nsis"
$expectedInstaller = Join-Path $nsisDir $installerName
$temporarySigningConfig = $null

Remove-Item -Force $expectedInstaller -ErrorAction SilentlyContinue
Push-Location "$PSScriptRoot\..\apps\desktop-tauri"
try {
    Invoke-Native { npm ci }
    if ($Channel -eq "Internal") {
        Invoke-Native { npm run tauri:nsis:unsigned }
    } else {
        $temporarySigningConfig = Join-Path ([System.IO.Path]::GetTempPath()) "minos-tauri-signing-$([guid]::NewGuid().ToString('N')).json"
        @{
            bundle = @{
                windows = @{
                    certificateThumbprint = $CertificateThumbprint
                    digestAlgorithm = "sha256"
                    timestampUrl = "http://timestamp.digicert.com"
                    tsp = $true
                }
            }
        } | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $temporarySigningConfig
        Invoke-Native { npm run tauri:nsis:signed -- --config $temporarySigningConfig }
    }
} finally {
    Pop-Location
    if ($temporarySigningConfig) {
        Remove-Item -LiteralPath $temporarySigningConfig -Force -ErrorAction SilentlyContinue
    }
}

$releaseOut = Join-Path $repo "dist\build\out"
if (-not (Test-Path $expectedInstaller)) {
    throw "Expected installer was not generated: $expectedInstaller"
}
New-Item -ItemType Directory -Force $releaseOut | Out-Null
Remove-Item -Force (Join-Path $releaseOut '*.exe') -ErrorAction SilentlyContinue
if ($Channel -eq "Production") {
    $signature = Get-AuthenticodeSignature $expectedInstaller
    if ($signature.Status -ne "Valid") {
        throw "Production installer Authenticode status is $($signature.Status), expected Valid."
    }
    Copy-Item -Force $expectedInstaller (Join-Path $releaseOut $installerName)
} else {
    Copy-Item -Force $expectedInstaller (Join-Path $releaseOut $internalInstallerName)
}

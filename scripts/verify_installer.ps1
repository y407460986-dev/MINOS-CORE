param(
    [Parameter(Mandatory = $true)]
    [string] $Installer,
    [switch] $RequireSignature,
    [string] $TestToken = "minos-installer-smoke-token"
)

$ErrorActionPreference = "Stop"

function Get-FreeTcpPort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try {
        return ([System.Net.IPEndPoint] $listener.LocalEndpoint).Port
    } finally {
        $listener.Stop()
    }
}

function Get-InstalledProcesses {
    param(
        [Parameter(Mandatory = $true)]
        [string] $InstallRoot
    )

    $root = [System.IO.Path]::GetFullPath($InstallRoot).TrimEnd('\') + '\'
    return @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        try {
            $_.Path -and [System.IO.Path]::GetFullPath($_.Path).StartsWith(
                $root,
                [System.StringComparison]::OrdinalIgnoreCase
            )
        } catch {
            $false
        }
    })
}

function Get-InstalledMainExecutable {
    param(
        [Parameter(Mandatory = $true)]
        [string] $InstallRoot
    )

    $mainExecutableMatches = @(Get-ChildItem -LiteralPath $InstallRoot -Filter "*.exe" -File |
        Where-Object {
            $_.Name -ne "uninstall.exe" -and
            $_.Name -notlike "minos-desktop-api*.exe"
        })
    if ($mainExecutableMatches.Count -ne 1) {
        throw "Installed application must contain exactly one main executable; found $($mainExecutableMatches.Count)."
    }
    return $mainExecutableMatches[0]
}

function Wait-FileUnlocked {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,
        [int] $TimeoutMilliseconds = 10000
    )

    $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMilliseconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $stream = $null
        try {
            $stream = [System.IO.File]::Open(
                $Path,
                [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::ReadWrite,
                [System.IO.FileShare]::None
            )
            return
        } catch [System.IO.IOException] {
            Start-Sleep -Milliseconds 250
        } catch [System.UnauthorizedAccessException] {
            Start-Sleep -Milliseconds 250
        } finally {
            if ($stream) {
                $stream.Dispose()
            }
        }
    }
    throw "File remained locked for $TimeoutMilliseconds milliseconds: $Path"
}

$installerMatches = @(Get-ChildItem -Path $Installer -File -ErrorAction SilentlyContinue)
if ($installerMatches.Count -ne 1) {
    throw "Installer pattern must match exactly one file; matched $($installerMatches.Count): $Installer"
}
$installerPath = (Resolve-Path -LiteralPath $installerMatches[0].FullName).Path

if ($RequireSignature) {
    $signature = Get-AuthenticodeSignature $installerPath
    if ($signature.Status -ne "Valid") {
        throw "Installer Authenticode status is $($signature.Status), expected Valid."
    }
}

$smokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) "minos-installer-smoke-$([guid]::NewGuid().ToString('N'))"
$installDir = Join-Path $smokeRoot "app"
$runtimeDir = Join-Path $smokeRoot "runtime"
$dbPath = Join-Path $runtimeDir "minos_desktop.sqlite3"
$outputDir = Join-Path $runtimeDir "out"
$mainProcess = $null
$sidecarProcess = $null
$uninstaller = $null

New-Item -ItemType Directory -Force $runtimeDir, $outputDir | Out-Null

try {
    $installProcess = Start-Process -FilePath $installerPath -ArgumentList @(
        "/S",
        "/D=$installDir"
    ) -Wait -PassThru
    if ($installProcess.ExitCode -ne 0) {
        throw "Silent install failed with exit code $($installProcess.ExitCode)."
    }

    $uninstaller = Get-ChildItem -LiteralPath $installDir -Recurse -Filter "uninstall.exe" -File | Select-Object -First 1
    $mainExecutable = Get-InstalledMainExecutable -InstallRoot $installDir
    $sidecarExecutable = Get-ChildItem -LiteralPath $installDir -Recurse -Filter "minos-desktop-api*.exe" -File |
        Where-Object { $_.Name -ne "uninstall.exe" } |
        Select-Object -First 1
    if (-not $uninstaller -or -not $mainExecutable -or -not $sidecarExecutable) {
        throw "Installed application is missing the main executable, sidecar, or uninstaller."
    }

    $previousToken = [Environment]::GetEnvironmentVariable("MINOS_DESKTOP_API_TOKEN", "Process")
    [Environment]::SetEnvironmentVariable("MINOS_DESKTOP_API_TOKEN", $TestToken, "Process")
    try {
        $mainProcess = Start-Process -FilePath $mainExecutable.FullName -PassThru -WindowStyle Hidden
    } finally {
        [Environment]::SetEnvironmentVariable("MINOS_DESKTOP_API_TOKEN", $previousToken, "Process")
    }

    $port = Get-FreeTcpPort
    $sidecarProcess = Start-Process -FilePath $sidecarExecutable.FullName -PassThru -WindowStyle Hidden -ArgumentList @(
        "--host", "127.0.0.1",
        "--port", "$port",
        "--db-path", $dbPath,
        "--output-dir", $outputDir,
        "--token", $TestToken
    )

    $healthUri = "http://127.0.0.1:$port/api/health"
    $authorized = $null
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            $authorized = Invoke-WebRequest -UseBasicParsing -Uri $healthUri -Headers @{
                Authorization = "Bearer $TestToken"
            } -TimeoutSec 2
            if ($authorized.StatusCode -eq 200) {
                break
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $authorized -or $authorized.StatusCode -ne 200) {
        throw "Installed sidecar did not become healthy within 30 seconds."
    }

    $unauthorizedStatus = $null
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUri -TimeoutSec 2
        $unauthorizedStatus = $response.StatusCode
    } catch {
        if ($_.Exception.Response) {
            $unauthorizedStatus = [int] $_.Exception.Response.StatusCode
        }
    }
    if ($unauthorizedStatus -ne 401) {
        throw "Unauthenticated health request returned $unauthorizedStatus, expected 401."
    }
} finally {
    foreach ($process in @($sidecarProcess, $mainProcess)) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            $process.WaitForExit(10000) | Out-Null
        }
        if ($process) {
            $process.Dispose()
        }
    }
    Get-InstalledProcesses -InstallRoot $installDir | ForEach-Object {
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
    for ($attempt = 0; $attempt -lt 40 -and (Get-InstalledProcesses -InstallRoot $installDir).Count; $attempt++) {
        Start-Sleep -Milliseconds 250
    }
    if ((Get-InstalledProcesses -InstallRoot $installDir).Count) {
        throw "Installed application processes did not exit before uninstall."
    }
    if ($sidecarExecutable -and (Test-Path -LiteralPath $sidecarExecutable.FullName)) {
        Wait-FileUnlocked -Path $sidecarExecutable.FullName
    }
    if ($uninstaller -and (Test-Path -LiteralPath $uninstaller.FullName)) {
        $uninstallProcess = Start-Process -FilePath $uninstaller.FullName -ArgumentList "/S" -Wait -PassThru
        if ($uninstallProcess.ExitCode -ne 0) {
            throw "Silent uninstall failed with exit code $($uninstallProcess.ExitCode)."
        }
    }
    for ($attempt = 0; $attempt -lt 40 -and (Test-Path -LiteralPath $installDir); $attempt++) {
        Start-Sleep -Milliseconds 250
    }
    if (Test-Path -LiteralPath $installDir) {
        throw "Silent uninstall did not remove the installation directory: $installDir"
    }
    Remove-Item -LiteralPath $smokeRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Output "Installer verification passed: $installerPath"

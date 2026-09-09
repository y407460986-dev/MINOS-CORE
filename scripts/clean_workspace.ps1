[CmdletBinding()]
param(
    [string[]] $Path = @(),
    [switch] $Apply
)

$ErrorActionPreference = "Stop"
$repo = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$AllowedRelativePaths = @(
    "build",
    "dist",
    "out",
    "release",
    "apps/desktop-tauri/dist",
    "apps/desktop-tauri/src-tauri/target"
)
$allowedPaths = @(
    $AllowedRelativePaths | ForEach-Object {
        [System.IO.Path]::GetFullPath((Join-Path $repo $_))
    }
)

$requestedPaths = if ($Path.Count -eq 0) { $AllowedRelativePaths } else { $Path }
foreach ($requestedPath in $requestedPaths) {
    $candidatePath = [System.IO.Path]::GetFullPath((Join-Path $repo $requestedPath))
    if ($candidatePath -notin $allowedPaths) {
        throw "Refusing path outside the cleanup allowlist: $requestedPath"
    }
    if (-not (Test-Path -LiteralPath $candidatePath)) {
        Write-Host "Skip missing: $requestedPath"
        continue
    }

    $item = Get-Item -LiteralPath $candidatePath -Force
    if ($item.LinkType -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw "Refusing reparse point or symbolic link: $requestedPath"
    }
    if (-not $Apply) {
        Write-Host "Would remove: $candidatePath"
        continue
    }

    Remove-Item -LiteralPath $candidatePath -Recurse -Force
    Write-Host "Removed: $candidatePath"
}

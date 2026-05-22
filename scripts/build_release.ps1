$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

& "$PSScriptRoot\build_sidecar.ps1"
Push-Location "$PSScriptRoot\..\apps\desktop-tauri"
try {
    npm ci
    npm run tauri:nsis
} finally {
    Pop-Location
}

$releaseOut = Join-Path $repo "dist\build\out"
$nsisDir = Join-Path $repo "apps\desktop-tauri\src-tauri\target\release\bundle\nsis"
New-Item -ItemType Directory -Force $releaseOut | Out-Null
Copy-Item -Force (Join-Path $nsisDir "*.exe") $releaseOut

$ErrorActionPreference = "Stop"

& "$PSScriptRoot\build_sidecar.ps1"
Push-Location "$PSScriptRoot\..\apps\desktop-tauri"
try {
    npm ci
    npm run release:nsis
} finally {
    Pop-Location
}

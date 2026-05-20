$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $repo ".venv-build"
$python = Join-Path $venv "Scripts\python.exe"
$pip = Join-Path $venv "Scripts\pip.exe"
$pyinstaller = Join-Path $venv "Scripts\pyinstaller.exe"
$sidecarName = "minos-desktop-api-x86_64-pc-windows-msvc"
$sourceDir = Join-Path $repo "dist\$sidecarName"
$dest = Join-Path $repo "apps\desktop-tauri\src-tauri\binaries"
$destDir = Join-Path $dest $sidecarName

python -m venv $venv
& $python -m pip install --upgrade pip
& $pip install -e "${repo}[desktop-api,ocr]" pyinstaller
& $pyinstaller --noconfirm --clean `
    --distpath (Join-Path $repo "dist") `
    --workpath (Join-Path $repo "build") `
    (Join-Path $repo "minos-desktop-api.spec")

New-Item -ItemType Directory -Force $dest | Out-Null
if (Test-Path $destDir) {
    Remove-Item -Recurse -Force $destDir
}
Copy-Item -Recurse -Force $sourceDir $dest
Copy-Item -Force `
    (Join-Path $sourceDir "$sidecarName.exe") `
    (Join-Path $dest "$sidecarName.exe")

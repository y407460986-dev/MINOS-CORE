$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $repo ".venv-build"
$python = Join-Path $venv "Scripts\python.exe"
$pyinstaller = Join-Path $venv "Scripts\pyinstaller.exe"
$lockFile = Join-Path $repo "requirements\locks\windows-py311.txt"
$sidecarName = "minos-desktop-api-x86_64-pc-windows-msvc"
$sourceDir = Join-Path $repo "dist\$sidecarName"
$dest = Join-Path $repo "apps\desktop-tauri\src-tauri\binaries"
$destDir = Join-Path $dest $sidecarName

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

Invoke-Native { python -m venv $venv }
Invoke-Native { & $python -m pip install --upgrade pip }
Invoke-Native { & $python -m pip install -r $lockFile }
Invoke-Native { & $python -m pip install -e $repo --no-deps }
Invoke-Native {
    & $pyinstaller --noconfirm --clean `
        --distpath (Join-Path $repo "dist") `
        --workpath (Join-Path $repo "build") `
        (Join-Path $repo "minos-desktop-api.spec")
}

New-Item -ItemType Directory -Force $dest | Out-Null
if (Test-Path $destDir) {
    Remove-Item -Recurse -Force $destDir
}
Remove-Item -Force (Join-Path $dest "$sidecarName.exe") -ErrorAction SilentlyContinue
Copy-Item -Recurse -Force $sourceDir $dest
Copy-Item -Force `
    (Join-Path $sourceDir "$sidecarName.exe") `
    (Join-Path $dest "$sidecarName.exe")

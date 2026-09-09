from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
TAURI_CONFIG_PATH = REPO_ROOT / "apps/desktop-tauri/src-tauri/tauri.conf.json"
NSIS_TEMPLATE_PATH = REPO_ROOT / "apps/desktop-tauri/src-tauri/nsis/installer.nsi"
BUILD_RELEASE_SCRIPT_PATH = REPO_ROOT / "scripts/build_release.ps1"
BUILD_SIDECAR_SCRIPT_PATH = REPO_ROOT / "scripts/build_sidecar.ps1"
VERIFY_INSTALLER_SCRIPT_PATH = REPO_ROOT / "scripts/verify_installer.ps1"
WINDOWS_RELEASE_WORKFLOW_PATH = REPO_ROOT / ".github/workflows/windows-release.yml"
CI_WORKFLOW_PATH = REPO_ROOT / ".github/workflows/ci.yml"
PACKAGE_JSON_PATH = REPO_ROOT / "apps/desktop-tauri/package.json"


def test_tauri_uses_repo_owned_nsis_template() -> None:
    tauri_config = json.loads(TAURI_CONFIG_PATH.read_text(encoding="utf-8"))

    assert tauri_config["bundle"]["windows"]["nsis"]["template"] == "nsis/installer.nsi"
    assert NSIS_TEMPLATE_PATH.exists()


def test_nsis_template_skips_stale_uninstall_registry_entry() -> None:
    template = NSIS_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "{{main_binary_path}}" in template
    assert "Function PageLeaveReinstall" in template
    assert "minos_skip_stale_uninstaller" in template
    assert 'IfFileExists "$4\\uninstall.exe" 0 minos_skip_stale_uninstaller' in template
    assert "ExecWait '$R1' $0" in template
    nsis_branch = template.split('ReadRegStr $4 SHCTX "${MANUPRODUCTKEY}" ""', maxsplit=1)[1].split(
        "${EndIf}", maxsplit=1
    )[0]
    assert nsis_branch.index(
        'IfFileExists "$4\\uninstall.exe" 0 minos_skip_stale_uninstaller'
    ) < nsis_branch.index("ExecWait '$R1' $0")


def test_nsis_template_does_not_restore_missing_install_location() -> None:
    template = NSIS_TEMPLATE_PATH.read_text(encoding="utf-8")

    restore_function = template.split("Function RestorePreviousInstallLocation", maxsplit=1)[1].split(
        "FunctionEnd", maxsplit=1
    )[0]

    assert 'IfFileExists "$4\\uninstall.exe" 0 restore_done' in restore_function
    assert restore_function.index('IfFileExists "$4\\uninstall.exe" 0 restore_done') < restore_function.index(
        "StrCpy $INSTDIR $4"
    )


def test_release_scripts_fail_fast_for_native_commands_and_copy_expected_installer() -> None:
    release_script = BUILD_RELEASE_SCRIPT_PATH.read_text(encoding="utf-8")
    sidecar_script = BUILD_SIDECAR_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "function Invoke-Native" in release_script
    assert "function Invoke-Native" in sidecar_script
    assert "$LASTEXITCODE -ne 0" in release_script
    assert "$LASTEXITCODE -ne 0" in sidecar_script
    assert 'Copy-Item -Force (Join-Path $nsisDir "*.exe") $releaseOut' not in release_script
    assert '$installerName = "$($tauriConfig.productName)_$($tauriConfig.version)_x64-setup.exe"' in release_script
    assert "Remove-Item -Force (Join-Path $releaseOut '*.exe')" in release_script


def test_release_build_separates_unsigned_internal_and_signed_production_channels() -> None:
    release_script = BUILD_RELEASE_SCRIPT_PATH.read_text(encoding="utf-8")
    package_json = json.loads(PACKAGE_JSON_PATH.read_text(encoding="utf-8"))

    assert "[ValidateSet(\"Internal\", \"Production\")]" in release_script
    assert "internal-unsigned" in release_script
    assert "CertificateThumbprint is required for Production" in release_script
    assert "Get-AuthenticodeSignature" in release_script
    assert "Status -ne \"Valid\"" in release_script
    assert "tauri:nsis:unsigned" in package_json["scripts"]
    assert "--no-sign" in package_json["scripts"]["tauri:nsis:unsigned"]
    assert "tauri:nsis:signed" in package_json["scripts"]
    assert "--no-sign" not in package_json["scripts"]["tauri:nsis:signed"]


def test_installer_verifier_checks_unique_match_auth_health_and_cleanup() -> None:
    verifier = VERIFY_INSTALLER_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "Resolve-Path" in verifier
    assert "$installerMatches.Count -ne 1" in verifier
    assert '"/S"' in verifier
    assert '"/D=$installDir"' in verifier
    assert "MINOS_DESKTOP_API_TOKEN" in verifier
    assert "Authorization = \"Bearer $TestToken\"" in verifier
    assert "$unauthorizedStatus -ne 401" in verifier
    assert "Get-AuthenticodeSignature" in verifier
    assert "Stop-Process" in verifier
    assert "Get-InstalledProcesses" in verifier
    assert "processes did not exit before uninstall" in verifier
    assert "uninstall.exe" in verifier
    assert "Start-Process -FilePath $installerPath" in verifier
    assert "$installProcess.ExitCode -ne 0" in verifier


def test_installer_verifier_locates_main_executable_and_waits_for_uninstall() -> None:
    verifier = VERIFY_INSTALLER_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "function Get-InstalledMainExecutable" in verifier
    assert '-Filter "MINOS-CORE.exe"' not in verifier
    assert 'Get-ChildItem -LiteralPath $InstallRoot -Filter "*.exe" -File' in verifier
    assert '$_.Name -ne "uninstall.exe"' in verifier
    assert '$_.Name -notlike "minos-desktop-api*.exe"' in verifier
    assert "$mainExecutableMatches.Count -ne 1" in verifier
    assert "Start-Process -FilePath $uninstaller.FullName" in verifier
    assert 'ArgumentList "/S"' in verifier
    assert "-Wait" in verifier
    assert "-PassThru" in verifier
    assert "$uninstallProcess.ExitCode -ne 0" in verifier
    assert "function Wait-FileUnlocked" in verifier
    assert "Wait-FileUnlocked -Path $sidecarExecutable.FullName" in verifier


def test_windows_release_workflow_verifies_before_draft_release() -> None:
    workflow = yaml.safe_load(WINDOWS_RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8"))
    ci_workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert set(workflow["on"]) == {"workflow_dispatch", "push"}
    assert workflow["on"]["push"]["tags"] == ["v*"]
    ci_triggers = ci_workflow.get("on", ci_workflow.get(True))
    assert "release" not in ci_triggers

    production = workflow["jobs"]["production-signed"]
    assert production["runs-on"] == "windows-latest"
    assert production["environment"] == "windows-release-signing"
    steps = production["steps"]
    names = [step.get("name") for step in steps]
    verify_signature = names.index("Verify Authenticode signature")
    install_smoke = names.index("Verify installed application")
    draft_release = names.index("Create draft release")
    assert verify_signature < install_smoke < draft_release

    secret_check = next(step["run"] for step in steps if step.get("name") == "Validate signing secrets")
    assert "WINDOWS_CERT_PFX_BASE64" in secret_check
    assert "WINDOWS_CERT_PASSWORD" in secret_check
    assert "exit 1" in secret_check
    assert names[-1] == "Remove signing certificate"

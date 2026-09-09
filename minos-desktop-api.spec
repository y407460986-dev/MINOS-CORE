# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_submodules
from pathlib import Path

block_cipher = None
repo_root = Path(SPECPATH)

collected_datas = [(str(repo_root / "configs"), "configs")]
collected_binaries = []
collected_hiddenimports = [
    "fastapi",
    "sse_starlette",
    "uvicorn.lifespan.on",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
]
collected_hiddenimports += collect_submodules("minos_core")
collected_hiddenimports += collect_submodules("minos_desktop")

for package in ("onnxruntime", "rapidocr_onnxruntime", "fitz", "PIL", "keyring", "jaraco"):
    datas, binaries, hiddenimports = collect_all(package)
    collected_datas += datas
    collected_binaries += binaries
    collected_hiddenimports += hiddenimports

collected_hiddenimports += [
    "keyring.backends.Windows",
    "keyring.backends.fail",
    "keyring.backends.null",
    "win32ctypes",
    "win32ctypes.pywin32",
    "win32ctypes.pywin32.win32cred",
]

a = Analysis(
    ["scripts/entrypoint_desktop_api.py"],
    pathex=[str(repo_root)],
    binaries=collected_binaries,
    datas=collected_datas,
    hiddenimports=collected_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "notebook"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="minos-desktop-api-x86_64-pc-windows-msvc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="minos-desktop-api-x86_64-pc-windows-msvc",
)

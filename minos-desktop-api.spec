# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all
from pathlib import Path

block_cipher = None
repo_root = Path(SPECPATH)

collected_datas = [(str(repo_root / "configs"), "configs")]
collected_binaries = []
collected_hiddenimports = [
    "fastapi",
    "sse_starlette",
    "minos_core",
    "minos_core.config",
    "minos_core.knowledge_base",
    "minos_core.knowledge_recommendation",
    "minos_core.part_family_knowledge",
    "uvicorn.lifespan.on",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "minos_core.pipeline",
    "minos_desktop",
    "minos_desktop.app_state",
    "minos_desktop.chain_state",
    "minos_desktop.services",
    "minos_desktop.table_editor",
    "minos_desktop.api",
    "minos_desktop.api.app",
    "minos_desktop.api.auth",
    "minos_desktop.api.cli",
    "minos_desktop.api.jobs",
    "minos_desktop.api.routes_closure",
    "minos_desktop.api.routes_exports",
    "minos_desktop.api.routes_health",
    "minos_desktop.api.routes_knowledge",
    "minos_desktop.api.routes_projects",
    "minos_desktop.api.routes_runs",
    "minos_desktop.api.routes_settings",
    "minos_desktop.api.routes_sse",
    "minos_desktop.api.routes_tables",
    "minos_desktop.api.schemas",
    "minos_desktop.api.sse",
]

for package in ("onnxruntime", "rapidocr_onnxruntime", "fitz", "PIL"):
    datas, binaries, hiddenimports = collect_all(package)
    collected_datas += datas
    collected_binaries += binaries
    collected_hiddenimports += hiddenimports

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

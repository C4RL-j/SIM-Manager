# -*- mode: python ; coding: utf-8 -*-
"""Windows x64 onedir build. Invoke through tools/Build-Portable.ps1."""

import os
from pathlib import Path
import tomllib

from PyInstaller.utils.hooks import copy_metadata


project_root = Path(SPECPATH).resolve().parent
version = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
run_root = Path(os.environ["SIM_MANAGER_BUILD_ROOT"]).resolve()
if not run_root.is_relative_to(project_root / "dist" / "portable"):
    raise ValueError("Portable build output must remain inside dist/portable.")
generated = run_root / "generated"
bundle_name = f"SIMManager-{version}-win-x64"

# Include only declared runtime assets. Never collect the working directory,
# tests, private discovery captures, user profiles or development environments.
datas = []
for pattern in ("resources/*.json", "resources/*.pem", "resources/*.png", "carriers/dito/*.js"):
    for source in sorted((project_root / "src" / "sim_manager").glob(pattern)):
        datas.append((str(source), str(source.parent.relative_to(project_root / "src"))))

# Version lookup needs distribution metadata, not editable-install workstation
# paths or direct_url.json. Include only standard public metadata files.
for source, destination in copy_metadata("sim-manager"):
    for name in ("METADATA", "WHEEL"):
        item = Path(source) / name
        if item.is_file():
            datas.append((str(item), destination))

analysis = Analysis(
    [str(project_root / "packaging" / "entrypoint.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=datas,
    # These imports are normally deferred until official carrier sign-in.
    # Explicit inclusion activates PyInstaller's maintained Qt WebEngine hooks
    # without opening a browser or changing the application's login flow.
    hiddenimports=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "sim_manager.ui.release_smoke"],
    hookspath=[str(project_root / "packaging" / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "tkinter", "pytest"],
    noarchive=False,
    optimize=0,
)
python_archive = PYZ(analysis.pure)
executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="SIMManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=True,
    icon=str(generated / "SIMManager.ico"),
    version=str(generated / "version-info.txt"),
    contents_directory="_internal",
    uac_admin=False,
)
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name=bundle_name,
)

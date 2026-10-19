"""Offline build preparation, inventory validation and portable ZIP creation."""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import platform
from pathlib import Path
import re
import shutil
import struct
import sys
import tomllib
import zipfile


PROJECT = Path(__file__).resolve().parent.parent
ASSET_PATTERNS = ("resources/*.json", "resources/*.pem", "resources/*.png", "carriers/dito/*.js")


class BuildFailure(Exception):
    """Only fixed build diagnostics are printed by this helper."""


def write_text(path: Path, text: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_root(value: str) -> Path:
    root = Path(value).resolve()
    portable = (PROJECT / "dist" / "portable").resolve()
    if not root.is_relative_to(portable) or root == portable or not root.is_dir():
        raise BuildFailure("Build root must be a fresh directory under dist/portable.")
    return root


def project_version() -> str:
    value = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if type(value) is not str or re.fullmatch(r"\d+\.\d+\.\d+", value) is None:
        raise BuildFailure("Portable builds require a three-part numeric project version.")
    module = ast.parse((PROJECT / "src" / "sim_manager" / "__init__.py").read_text(encoding="utf-8"))
    declared = [node.value.value for node in module.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)
                and isinstance(node.value, ast.Constant)]
    if declared != [value]:
        raise BuildFailure("Project metadata and sim_manager.__version__ must agree before building.")
    return value


def runtime_hashes() -> dict[str, str]:
    package = PROJECT / "src" / "sim_manager"
    sources = set(package.rglob("*.py"))
    for pattern in ASSET_PATTERNS:
        sources.update(package.glob(pattern))
    sources.update((PROJECT / "packaging").rglob("*"))
    sources.add(PROJECT / "pyproject.toml")
    sources.add(PROJECT / "tools" / "Build-Portable.ps1")
    return {
        path.relative_to(PROJECT).as_posix(): sha256(path)
        for path in sorted(sources)
        if path.is_file() and "__pycache__" not in path.parts
    }


def build_versions() -> dict[str, str]:
    versions = {"Python": platform.python_version()}
    requirements = (PROJECT / "packaging" / "requirements-build.txt").read_text(encoding="utf-8")
    for line in requirements.splitlines():
        if not line or line.startswith("#"):
            continue
        name, expected = line.split("==", 1)
        try:
            actual = metadata.version(name)
        except metadata.PackageNotFoundError:
            raise BuildFailure("Install packaging/requirements-build.txt before building.") from None
        if actual != expected:
            raise BuildFailure("Build dependency versions differ from packaging/requirements-build.txt.")
        versions[name] = actual
    return versions


def prepare(root: Path) -> None:
    if platform.system() != "Windows" or struct.calcsize("P") != 8 or platform.machine().lower() not in ("amd64", "x86_64"):
        raise BuildFailure("Use 64-bit Python on Windows x64 to build this portable release.")
    version, versions = project_version(), build_versions()
    generated = root / "generated"
    generated.mkdir()
    notices = generated / "THIRD_PARTY"
    notices.mkdir()
    manifest = json.loads((PROJECT / "packaging" / "licenses" / "SOURCES.json").read_text(encoding="utf-8"))
    for name, record in manifest.items():
        source = PROJECT / "packaging" / "licenses" / name
        if sha256(source) != record["sha256"]:
            raise BuildFailure("Vendored third-party license text failed its recorded checksum.")
        shutil.copyfile(source, notices / name)
    shutil.copyfile(PROJECT / "packaging" / "licenses" / "SOURCES.json", notices / "LICENSE-SOURCES.json")
    shutil.copyfile(Path(sys.base_prefix) / "LICENSE.txt", notices / "Python-LICENSE.txt")
    for name in ("PyInstaller", "PySide6-Essentials", "PySide6-Addons", "shiboken6"):
        distribution = metadata.distribution(name)
        for entry in distribution.files or ():
            if ".dist-info/" in str(entry) and Path(entry).name.lower().startswith(("license", "copying", "notice")):
                target = notices / "wheel-metadata" / name / Path(entry).name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(distribution.locate_file(entry), target)

    from PIL import Image
    with Image.open(PROJECT / "src" / "sim_manager" / "resources" / "sim-manager.png") as artwork:
        artwork.convert("RGBA").save(
            generated / "SIMManager.ico", format="ICO",
            sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)],
        )
    from PyInstaller.utils.win32.versioninfo import FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo
    numeric_version = (*map(int, version.split(".")), 0)
    info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=numeric_version, prodvers=numeric_version, mask=0x3F, flags=0,
                          OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
        kids=[StringFileInfo([StringTable("040904B0", [
            StringStruct("FileDescription", "SIM Manager"), StringStruct("FileVersion", version),
            StringStruct("OriginalFilename", "SIMManager.exe"), StringStruct("ProductName", "SIM Manager"),
            StringStruct("ProductVersion", version),
        ])]), VarFileInfo([VarStruct("Translation", [1033, 1200])])],
    )
    write_text(generated / "version-info.txt", str(info))
    state = {"version": version, "architecture": "win-x64", "build_versions": versions,
             "prepared_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "runtime_sha256": runtime_hashes()}
    write_text(generated / "build-info.json", json.dumps(state, indent=2) + "\n")
    print("Prepared portable Windows x64 build, icon, version resource and offline third-party notices.")


def finalize(root: Path) -> None:
    generated = root / "generated"
    state = json.loads((generated / "build-info.json").read_text(encoding="utf-8"))
    if state["runtime_sha256"] != runtime_hashes() or state["version"] != project_version():
        raise BuildFailure("Runtime or packaging sources changed during the build; build a fresh release.")
    version = state["version"]
    bundle = root / "app" / f"SIMManager-{version}-win-x64"
    executable = bundle / "SIMManager.exe"
    internal = bundle / "_internal"
    with executable.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise BuildFailure("Packaged executable is not a Windows PE file.")
        stream.seek(0x3C)
        offset = struct.unpack("<I", stream.read(4))[0]
        stream.seek(offset)
        if stream.read(6) != b"PE\x00\x00d\x86":
            raise BuildFailure("Packaged executable is not Windows x64.")
    python_dll = "python" + "".join(state["build_versions"]["Python"].split(".")[:2]) + ".dll"
    for required in (python_dll, "PySide6/QtWebEngineProcess.exe", "PySide6/Qt6Qml.dll",
                     "PySide6/Qt6Quick.dll", "PySide6/Qt6WebEngineCore.dll", "PySide6/resources/icudtl.dat",
                     "PySide6/resources/qtwebengine_resources.pak", "PySide6/translations/qtwebengine_locales/en-US.pak"):
        if not (internal / required).is_file():
            raise BuildFailure("Required bundled Python or Qt WebEngine runtime file is missing.")
    if (internal / "PySide6" / "qml").exists():
        raise BuildFailure("This Widgets-only application must not bundle unused QML import plugins.")
    package = PROJECT / "src" / "sim_manager"
    for pattern in ASSET_PATTERNS:
        for source in package.glob(pattern):
            target = internal / "sim_manager" / source.relative_to(package)
            if not target.is_file() or sha256(source) != sha256(target):
                raise BuildFailure("A declared application resource is missing or differs from source.")
    for path in bundle.rglob("*"):
        if path.is_symlink() or path.name.lower() in (".env", ".venv", "tests", "artifacts", "direct_url.json"):
            raise BuildFailure("The portable bundle contains an unexpected development/private path.")
    shutil.copytree(generated / "THIRD_PARTY", bundle / "THIRD_PARTY")
    write_text(bundle / "BUILD-INFO.json", json.dumps(state, indent=2) + "\n")
    write_text(bundle / "README-PORTABLE.txt", f"""SIM Manager {version} - Windows x64 portable

Extract the complete ZIP into a folder, then open SIMManager.exe.
Keep _internal beside the executable. Python and Qt are bundled; no separate
Python installation or administrator access is required. Do not run from inside
the ZIP. This build is unsigned.

Use --demo for a clearly marked offline demonstration. Normal mode uses the
existing local D2 router and official MyDITO sign-in flow. Enter credentials only
in the application's dialogs. Saved profiles/settings use the current Windows
user's application storage; the application folder is portable, not user data.
Closing the window can keep SIM Manager running in the tray according to
Settings. Choose Exit in the tray menu to stop it.

Source and build instructions: https://github.com/C4RL-j/SIM-Manager
See THIRD_PARTY_NOTICES.txt and THIRD_PARTY for bundled library notices.
BUILD-INFO.json records the exact dependency versions and source hashes.
""")
    qt_version = state["build_versions"]["PySide6-Essentials"]
    write_text(bundle / "THIRD_PARTY_NOTICES.txt", f"""Third-party software used by SIM Manager

Python {state['build_versions']['Python']} - Python Software Foundation and contributors.
License and bundled component notices: THIRD_PARTY/Python-LICENSE.txt.
Source: https://www.python.org/downloads/source/

Qt / Qt for Python (PySide6 and Shiboken6) {qt_version}
Copyright The Qt Company Ltd. and other contributors.
This distribution uses the community LGPL licensing option, including LGPLv3
for Qt/PySide6/Shiboken. Full LGPLv3 and its incorporated GPLv3 text are included.
Qt WebEngine also contains Chromium and its component-specific license terms,
including LGPLv2.1 where applicable. THIRD_PARTY contains the official Qt 6.11.2
component attribution/license detail text with source URLs and recorded hashes.
This reference may include optional/platform components not linked in this build.
The unmodified wheel metadata notices are also preserved there; inclusion of a
commercial-option notice does not select or claim a commercial Qt license.

The native Qt libraries remain separate in _internal/PySide6 and can be replaced
with compatible modified libraries. Modification of those libraries and reverse
engineering for debugging such modifications are permitted under their licenses.
Corresponding upstream sources:
https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-{qt_version}-src/
https://code.qt.io/cgit/qt/qtbase.git/tag/?h=v{qt_version}
https://code.qt.io/cgit/qt/qtwebengine.git/tag/?h=v{qt_version}
https://code.qt.io/cgit/qt/qtwebengine-chromium.git/tree/?id=5170777d28bee1ce92cc693a0dbf2ad01492e5cf
Complete Qt {qt_version} sources (including bundled Chromium):
https://download.qt.io/official_releases/qt/6.11/{qt_version}/single/
Qt module licensing and attributions: https://doc.qt.io/qt-6/licensing.html
https://doc.qt.io/qt-6/qtwebengine-licensing.html

PyInstaller {state['build_versions']['PyInstaller']} bootloader
Copyright PyInstaller Development Team. GPLv2-or-later with bootloader exception.
The full license and exception are preserved under THIRD_PARTY/wheel-metadata.
Source: https://github.com/pyinstaller/pyinstaller

Other component notices remain governed by their respective full license texts.
""")
    for name in ("LICENSE", "LICENSE.txt", "LICENSE.md"):
        source = PROJECT / name
        if source.is_file():
            shutil.copyfile(source, bundle / name)
    archive = root / f"{bundle.name}.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for source in sorted(bundle.rglob("*")):
            if source.is_file():
                output.write(source, source.relative_to(bundle.parent))
    with zipfile.ZipFile(archive) as output:
        if output.testzip() is not None:
            raise BuildFailure("The newly created portable archive failed its integrity check.")
    write_text(root / f"{archive.name}.sha256", f"{sha256(archive)}  {archive.name}\n")
    print(f"Portable folder: {bundle}")
    print(f"Portable archive: {archive}")
    print(f"SHA256: {sha256(archive)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("prepare", "finalize"))
    parser.add_argument("--run-root", required=True)
    args = parser.parse_args()
    try:
        root = checked_root(args.run_root)
        (prepare if args.step == "prepare" else finalize)(root)
    except BuildFailure as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

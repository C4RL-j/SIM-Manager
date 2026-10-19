# Windows portable build

Build on Windows x64 using Python 3.13.15 and the pinned release dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r packaging/requirements-build.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
powershell -NoProfile -ExecutionPolicy Bypass -File tools/Build-Portable.ps1
```

The script reads the existing project version, checks it against
`sim_manager.__version__`, and creates a new timestamped directory under ignored
`dist/portable/`. Existing builds are retained. The resulting portable folder,
ZIP and SHA256 file contain Python, Qt Widgets, Qt WebEngine, the helper renderer,
resources/locales, declared application assets, a usage README, build information
and third-party notices. Extract the entire ZIP; keep `_internal` with the EXE.

The QtQml hook preserves normal native QtQml/QtQuick dependencies while omitting
the unrelated installed QML import plugin tree. This application uses Widgets
and QtWebEngineWidgets and loads no QML documents. The maintained PyInstaller
WebEngine hook still collects its renderer, resources and locales. The build
rejects missing required DLLs/assets and an unexpected QML import directory.
Verify the frozen `QWebEngineView`, not only Python imports, before release.

Build preparation is offline. `licenses/SOURCES.json` records hashes and source
URLs for the vendored license/attribution reference files. The Qt 6.11.2 notices
include the relevant module and Chromium component details from the official
versioned documentation; the reference also lists optional/platform components
that may not be linked in the Windows application. The full Qt 6.11.2 source
distribution is available at:

https://download.qt.io/official_releases/qt/6.11/6.11.2/single/

The build records source hashes and stops if runtime/packaging sources change
between preparation and finalization. Freeze source edits before building. The
artifact is unsigned; the script does not create an installer, modify runtime
authentication, fetch account data, publish a release or change the app version.

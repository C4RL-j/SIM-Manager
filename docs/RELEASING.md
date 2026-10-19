# Windows portable release

Build on Windows x64 with 64-bit Python 3.13 and the pinned dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r packaging/requirements-build.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
powershell -NoProfile -ExecutionPolicy Bypass -File tools/Build-Portable.ps1
```

The builder creates a fresh timestamped directory under `dist/portable/` and
preserves failed builds for inspection. It checks project/application version
agreement, dependency versions, source hashes, x64 PE structure, Python/Qt
WebEngine components, declared resources and ZIP integrity. It bundles the
application icon, Windows version information and third-party notices.

Distribute the complete `SIMManager-<version>-win-x64.zip` and its `.sha256` file.
The ZIP contains `SIMManager.exe` plus `_internal` dependencies; the EXE is not a
standalone file. No Python installation or administrator access is needed.
These builds are unsigned unless a separate reviewed signing step is added.

Before publishing, run the backend, GUI and JavaScript suites from the repository
root. Test the packaged EXE with its explicit offline diagnostic:

```powershell
& '<portable folder>\SIMManager.exe' --release-smoke '<new report path>.json'
```

Choose a new report path; existing files are never overwritten. Expect exit 0,
`passed: true`, the release version and `frozen: true`. This check uses synthetic
memory providers and a network-blocked blank WebEngine page. It bypasses normal
account/router access, user stores, Windows startup registration and production
instance activation. Check that the launched process and its browser children
exit cleanly. Keep reports and all local evidence out of Git/release assets.

Review the complete source/history and staged files before public publication.
Tag the tested commit, publish the ZIP/checksum, verify the public repository and
release tag, then download the assets into a fresh directory and compare SHA-256.
Smoke-test the downloaded artifact too. Do not upload build environments, private
captures, logs, user profiles, credentials or real account data.

Start with Windows is an opt-in current-user setting for the frozen executable.
Move the portable folder only after disabling it, then enable it from the new
location. Close-to-tray defaults on for new installs; saved choices remain intact.
Use the tray's Exit action before replacing/removing a running portable build.

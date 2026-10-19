# Windows executable and public GitHub release

User authorizes a Windows executable, versioned public GitHub publication, and a
startup option plus close-to-tray behavior. After the optional clarification
remained unanswered, startup is interpreted as Start with Windows (opt-in).
New installs default to close-to-tray; existing explicit preferences are preserved.

Published to the public `C4RL-j/SIM-Manager` repository using the existing project
version `v0.1.0`. Only reviewed application source and intentional release assets
were uploaded; existing authorized work was preserved.

- [x] Inspect repository/version/history/account/tooling and release constraints.
- [x] Audit all source/fixtures/history for private data before public upload.
- [x] Build repeatable Windows x64 portable PyInstaller executable, Qt WebEngine
  dependencies, branding, version metadata, notices, ZIP and SHA-256.
- [x] Add optional Start with Windows and retain explicit tray Exit.
- [x] Test source, isolated packaged executable and package contents.
- [x] Review/stage intentional source, commit and tag the tested version.
- [x] Create public repository, push source/tag, publish GitHub release/assets.
- [x] Verify public repository, release commit, assets and downloaded checksum.

No private account/router validation, credentials, automatic OTP, router settings,
SMS mutation, Smart support, History implementation or unrelated task is added.
Smoke checks use synthetic memory services and deny-all-network blank WebEngine.
No current user session will be closed to perform packaging tests.

Pre-publication results (2026-10-19):

- Source suites: 640 backend, 264 GUI and 79 JavaScript cases passed (983 total).
  Four smoke-helper tests and a native source check passed again after adding a
  real blank WebEngine view. Settings assertions were updated for the authorized
  startup checkbox and new close-to-tray default; production SMS was unchanged.
- All 17 checks passed against the actual frozen EXE, including real Widgets,
  branded tray/right-edge placement, zero/stale/expiry/SIM switching, a visible
  network-blocked blank WebEngine view and ordered view/page/profile cleanup.
  Process exit was 0; seven resources loaded; stderr was empty and no new browser
  process remained. Version and Windows PE product/file metadata are 0.1.0.
- Final ZIP: 185067038 bytes, 355 entries. SHA-256:
  `3485ad95c0a3ee1de5f67fbd31949afe1fb109f4efa70876d190d7db947097da`.
  All 80 runtime/build source hashes still matched after packaging. ZIP integrity,
  declared assets, x64 Python/Qt renderer/resources/locales and required native
  QtQml/QtQuick dependencies passed. Unused QML import plugins are excluded.
- Release files live under ignored `dist/portable/20261019-020022-1931646/`.
  The package contains the full dependency folder and notices; the EXE is not a
  standalone single-file distribution and is unsigned.
- Source/history audit reviewed all seven existing commits and 168 historical
  blobs. One user-supplied phone example in an uncommitted test was replaced by
  synthetic data. No credentials/private account captures were found. Staging
  excludes environments, private captures, logs, profiles and generated outputs.
- Notice source links/hashes were checked. Git attributes preserve exact notice
  bytes across Windows clones so recorded hashes remain valid. The initial build
  was superseded after correcting one source URL and omitting optional QML data.

Publication results (2026-10-19):

- Public repository: https://github.com/C4RL-j/SIM-Manager
- Latest stable release: https://github.com/C4RL-j/SIM-Manager/releases/tag/v0.1.0
  Published at `2026-10-19T02:25:39Z`; authenticated and anonymous API reads both
  confirmed the release is public, not a draft or prerelease, with two assets.
- Annotated tag `v0.1.0` points to source commit
  `3a9452d2ae76797a3335ba14d52c49d1fa52f781`. Main also receives this documentation
  completion record; the tested release tag and runtime sources remain unchanged.
- GitHub confirmed the ZIP's exact 185067038-byte size and SHA-256 above, plus
  the uploaded 95-byte checksum file. Both downloaded assets matched locally.
- A fresh extraction of the downloaded ZIP passed all 17 frozen EXE checks again:
  version 0.1.0, seven resources, exit 0, empty stderr and no new browser processes.
  An earlier local extraction also passed after renaming the EXE and clearing
  Python/Qt paths from the child environment. No account or router was accessed.
- The first download wrapper hit Windows PowerShell's missing process-exit-code
  reporting even though the application's report passed. A rerun with an explicit
  process handle in PowerShell 7 confirmed exit 0 and the same 17 passing checks.
- The remote source tree contained 169 reviewed files with no generated binaries,
  environments, logs, captures or databases. The final review also corrected the
  fresh-environment build recipe to install the project metadata before freezing.

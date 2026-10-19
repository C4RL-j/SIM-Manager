# Windows executable and public GitHub release

User authorizes a Windows executable, versioned public GitHub publication, and a
startup option plus close-to-tray behavior. After the optional clarification
remained unanswered, startup is interpreted as Start with Windows (opt-in).
New installs default to close-to-tray; existing explicit preferences are preserved.

Destination verified: authenticated GitHub user `C4RL-j`; no existing
`C4RL-j/SIM-Manager` repository, remote or version tags. First public release will
use the existing project version `v0.1.0`. Publish only reviewed application
source and intentional release assets; preserve existing authorized work.

- [x] Inspect repository/version/history/account/tooling and release constraints.
- [x] Audit all source/fixtures/history for private data before public upload.
- [x] Build repeatable Windows x64 portable PyInstaller executable, Qt WebEngine
  dependencies, branding, version metadata, notices, ZIP and SHA-256.
- [x] Add optional Start with Windows and retain explicit tray Exit.
- [x] Test source, isolated packaged executable and package contents.
- [ ] Review/stage intentional source, commit and tag the tested version.
- [ ] Create public repository, push source/tag, publish GitHub release/assets.
- [ ] Verify public repository, release commit, assets and downloaded checksum.

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

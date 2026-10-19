# Supplied SIM logo and application icon

Scope: use the exact user-provided `../assets/Glossy Green SIM Wi-Fi Icon.png`
as the sidebar logo and native application/window icon. Bundle it as a package
resource so installed builds do not depend on the workspace asset path. Preserve
the existing sidebar dimensions, page styling, services and all functionality.

- [x] Locate and inspect supplied image and existing Qt/resource setup.
- [x] Wire packaged image to sidebar and application/native window identity.
- [x] Verify existing GUI checks, native display, package bytes and scope.
- [x] Record results and complete this plan.

No artwork edits, new dependencies, executable packaging framework, shortcut
installation, backend/authentication changes or live router/account access.

## Completed

The exact supplied 1254x1254 transparent PNG is copied byte-for-byte into
`sim_manager.resources/sim-manager.png`. The existing icon module loads it through
importlib.resources, including installed packages. QApplication and MainWindow use
it as their icon; ordinary owned and unparented dialogs inherit the application
icon. The sidebar uses the same artwork at its existing 42x42 logical footprint,
with device-pixel-ratio-aware rendering and an accessible logo label. The old SM
text and colored tile are replaced with the transparent supplied image.

Windows startup sets a stable process AppUserModelID before creating Qt UI so the
Python-launched application has its own grouping identity. This is process-local,
uses no registry/shortcut changes, and safely falls back if unavailable. Native
window small/large icon handles and the expected process identity were verified.
The repository has no current executable packaging pipeline; this task does not
alter the Python interpreter's executable file icon or install shortcuts.

## Incremental files

- `src/sim_manager/resources/sim-manager.png` (new exact source copy)
- `src/sim_manager/ui/icons.py`
- `src/sim_manager/ui/main_window.py`
- `src/sim_manager/ui/theme.py` (brand mark only)
- `src/sim_manager/app.py`
- `pyproject.toml` (package PNG resources)
- `README.md`
- `plans/completed/012-app-branding.md` (this plan)

## Verification

- Existing full GUI suite: 225 tests passed in 72.666 seconds; no new tests needed
  for this reversible asset/presentation change.
- Native Windows source and packaged-wheel checks passed: transparent sidebar
  image, unchanged 42x42 logo footprint, application/main-window icon, nonzero
  WM_GETICON small/large handles, explicit process identity and inherited dialog
  icon. Synthetic provider only, no router, account or credential-store access.
- Native screenshot inspected under the existing theme; no layout change.
- Wheel build passed; all 59 runtime entries match source, including the PNG.
  Packaged PNG bytes match the original asset, and packaged native validation
  exits 0 without accessing the external assets directory.
- The original asset hash is unchanged. All 128 other preexisting project files
  match the baseline, including backends, services, authentication, Messages and
  account-data logic. Source Python/TOML and whitespace checks passed.
- Git status includes earlier work: 29 modified tracked files, 32 untracked,
  nothing staged. No commit or push.

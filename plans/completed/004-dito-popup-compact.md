# Compact MyDITO popup sizing

Scope: size, WebEngine zoom and existing presentation CSS spacing only. Keep the
current original official card, all DOM logic, fallback, authentication, isolated
session/security and Cancel unchanged. Preserve prior uncommitted popup work.

- [x] Inspect existing geometry, styling and tests; snapshot the task baseline.
- [x] Reduce normal/minimum popup size and use 88% WebEngine zoom.
- [x] Reduce existing CSS spacing while preserving responsive layout/scrolling.
- [x] Extend minimal existing GUI coverage for sizing, zoom and resizing.
- [x] Verify fresh public native rendering at normal and resized sizes.
- [x] Run regression suites, review scope/packaging and record results.

Completed 2026-10-09 (Asia/Irkutsk).

## Result

- Default size is 480×520; minimum is 420×500, with manual resizing retained.
- WebEngine zoom is 88%; native margins are 8px and layout spacing is 4px.
- Existing focused-card CSS uses smaller root/card/footer padding and an
  automatically sized legal row. The card stays centered; overflow is not
  clipped or disabled.
- Exact public native checks at 480×520, 420×500 and 620×660 showed the four
  original controls and both legal links visible, a centered card, and no
  horizontal or vertical scrolling. Native Cancel remained visible and closed
  the surface cleanly. Validation used fresh unauthenticated profiles with the
  view disabled; no credentials/OTP were entered or read.

## Verification

602 backend/service, 179 GUI and 63 Node tests passed: **844 total**, zero
failures. Existing GUI coverage was extended for default/minimum size, margins,
spacing, zoom, manual resizing and accessible Cancel; no new test cases were
added. The final full GUI run passed in 45.704 seconds.

Presentation JavaScript outside its CSS string is byte-for-byte identical to the
task baseline. Browser changes are confined to dimensions, margins, spacing and
zoom. Authentication, requests, security settings, session lifecycle, DOM guards,
observers and fallback remain unchanged. All 102 other baseline files match;
prior uncommitted work is preserved.

The wheel contains the exact changed browser/CSS resource bytes and excludes
tests/tools/legacy. All 78 Python AST parses and presentation JavaScript syntax
passed. Tracked/new-file whitespace and incremental diff review passed.

## Changed files for this sizing task

Updated:

- `src/sim_manager/carriers/dito/browser.py`
- `src/sim_manager/carriers/dito/login_focus.js` (CSS only)
- `tests/gui/test_dito_browser.py`
- `README.md`
- `docs/carriers/DITO.md`

Added:

- `plans/completed/004-dito-popup-compact.md`

Git remains unstaged with no commit created. Including the prior popup work,
`main` has seven modified tracked files and four new files.

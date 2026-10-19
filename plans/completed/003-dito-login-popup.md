# Focus the official MyDITO sign-in popup

Scope: visual presentation only in the existing isolated Qt WebEngine surface.
Keep the original official SMS form and all authentication/security/session
behavior. No cloned form, credentials/OTP access, authentication API investigation,
Task 12 or other feature work.

- [x] Inspect public login layout/CSS only for conservative selectors.
- [x] Add an optional isolated-world presentation script which centers the
  evidenced SMS card and hides safe chrome; restore full page on any mismatch.
- [x] Preserve native Cancel and original security challenges/consent/errors.
- [x] Add minimal synthetic script/browser tests and run regression suites.
- [x] Verify native/synthetic rendering, packaging, privacy/scope and Git state.
- [x] Record results and update relevant documentation.

Completed 2026-10-09 (Asia/Irkutsk).

## Result

The popup opens at 760×740, with a 540×500 minimum. A separately packaged,
optional DocumentReady/ApplicationWorld script styles the original official SMS
card. Exact public card/control/ancestor guards limit the changes. Known header,
decorations and marketing disappear only after protected-control checks. Known
desktop-width ancestors and footer wrappers resize without global overflow
clipping. Original Terms and Privacy links remain available. Native Cancel stays
outside the page.

Unknown login structure/mode/route, visible challenge/consent surfaces, and
presentation exceptions restore the site's original page. Styling does not read
input values, intercept credentials/OTP, clone or move controls, handle
authentication, or access browser storage/network. The existing MainWorld auth
observer, allowlist, TLS checks, memory-only profile, callbacks and shutdown are
unchanged. No Task 12, account data, Smart or other feature was started.

## Public presentation evidence

The public login asset `p__Login.a8b21259.async.js` and its CSS establish the
original root/layout/card/title selectors and native form structure. Common CSS
`common.76853765.chunk.css` establishes `pageComponent`'s max-content minimum
width and the 1200px footer. Their relevant public layout was checked again in a
fresh unauthenticated native WebEngine profile. No authentication API was
investigated for this change.

The native SMS input omits the component's HTML maxlength; both that verified
shape and maxlength=6 are accepted. Known marketing footer columns and three- or
four-link social image rows may hide only if their shape and protected-control
checks pass. Unfamiliar footer content remains available.

## Verification

- 602 backend/service, 179 GUI and 63 Node tests passed: **844 total**, zero
  failures. Added only two GUI and six synthetic Node cases.
- Tests cover preservation of original controls/legal links, unknown structure,
  SMS/password mode changes, challenges/consent, route/origin guards, delayed
  rendering, restoration, native Cancel and silent resource/insertion failure.
  Synthetic access guards reject input-value reads/writes, storage, network and
  console use by the presentation script.
- Fresh public native rendering passed at default and minimum popup sizes:
  centered card, all four original controls fitting horizontally, zero
  horizontal overflow and two preserved legal links. Smaller height keeps
  normal vertical scrolling. Final social clutter was hidden. Restoring the
  full page removed every owned attribute, and Cancel closed/disposed cleanly.
  The view was disabled throughout these checks; no credentials/OTP were
  entered, authentication attempted, or private screenshot retained.
- Wheel build passed using isolated build dependencies; the environment does
  not have setuptools for a non-isolated build. All 51 runtime entries include
  the exact presentation resource, unchanged certificate/demo bytes, and no
  tests/tools/legacy. All 78 Python AST parses, TOML and changed JavaScript syntax
  checks passed. Tracked/new-file whitespace review passed.
- All 97 pre-existing project files outside the seven updated files and all 40
  legacy file hashes match the task baseline. Authentication implementation and
  other features remain unchanged.

## Changed files

Updated:

- `AGENTS.md`
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/WORKFLOW.md`
- `docs/carriers/DITO.md`
- `src/sim_manager/carriers/dito/browser.py`
- `tests/gui/test_dito_browser.py`

Added:

- `src/sim_manager/carriers/dito/login_focus.js`
- `tests/test_dito_login_focus.js`
- `plans/completed/003-dito-login-popup.md`

Git: `main`, seven modified tracked files and three new files; nothing staged and
no commit created for this task.

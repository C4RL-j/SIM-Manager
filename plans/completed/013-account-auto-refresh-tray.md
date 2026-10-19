# Shared automatic account refresh and tray dashboard

Scope: one authenticated account scheduler shared by Home and a compact Qt tray
popup; Settings auto-refresh/15/30/60s and explicit opt-in close-to-tray; lifecycle,
rate-limit/backoff handling and ordinary application preferences. Reuse the one
existing MyDITO service/session/data source, D2/SMS services and SIM context guards.

- [x] Inspect current data/session lifecycle, theme, settings and constraints.
- [x] Implement one overlap-safe scheduler with expiry/rate-limit backoff.
- [x] Implement shared-data tray popup/icon, menu/actions and bounded placement.
- [x] Add saved public preferences, explicit close behavior and instance guard.
- [x] Integrate shared updates/actions; preserve zero/stale/unavailable semantics.
- [x] Run suites/native tray gestures/package/privacy/scope checks and document.

MyDITO sessions remain memory-only. Startup refresh may reuse a valid existing
session, but must never create a login, request OTP or restore session secrets.
AccountData has no verified total allowance; progress remains hidden rather than
parsing a denominator from resource names. Only public UI settings persist.
Closing defaults to Exit to preserve existing behavior until the user enables
close-to-tray. Missing system tray must never strand a hidden application.
All automated/native checks use synthetic services and private-data-free UI.

Implementation:

- `ui/account_refresh.py`: one shared timer and manual request gate, validated
  current-SIM eligibility, deferred startup/post-login deduplication, completion
  intervals, bounded automatic backoff, strict rate-limit cooldown and disposal.
- `ui/tray.py` and appended tray theme: one branded native icon, a compact navy
  popup, balance card, menu/actions, tooltip, shared normalized values, explicit
  unavailable/stale/reconnect states, work-area bounds and dismissal handling.
- `ui/preferences.py` and Settings: only three public options persist in native
  current-user Qt settings. Defaults are automatic refresh on/30 seconds and
  close-to-tray off. Invalid settings and save failures use safe fixed outcomes.
- `ui/single_instance.py`: a current-user process lock prevents duplicate Windows
  pipe owners; the restricted local channel accepts only fixed activation text.
- `app.py` and `ui/main_window.py`: wire the existing account service to the one
  scheduler and both views, keep hidden sessions active only when enabled,
  restore the main window and perform explicit bounded shutdown on Exit.
- Neutral account models/service and the existing MyDITO bridge/parser add only
  closed HTTP 429 outcomes and bounded Retry-After seconds. No new getter,
  authentication path, session export or private response logging is added.
- Home keeps its layout, manual action and last-verified values, and displays
  Reconnect DITO on expiry.

Files changed for this task (earlier uncommitted work was preserved):

- Runtime: `src/sim_manager/app.py`, `account_models.py`,
  `services/accounts.py`, `carriers/dito/account_data.py`,
  `carriers/dito/account_data.js`, `ui/main_window.py`, `ui/pages/home.py`,
  `ui/pages/settings.py`, `ui/theme.py`.
- New runtime: `src/sim_manager/ui/account_refresh.py`, `ui/preferences.py`,
  `ui/single_instance.py`, `ui/tray.py`.
- Tests: `tests/test_account_data_service.py`, `test_dito_account_data.py`,
  `test_dito_account_data.js`, `tests/gui/test_account_home.py`,
  `test_app_messages.py`, `test_desktop.py`, `test_sim_pages.py`.
- New GUI tests: `tests/gui/test_account_refresh.py`, `test_background_app.py`,
  `test_preferences.py`, `test_single_instance.py`, `test_tray.py`.
- Documentation: `README.md`, `docs/ARCHITECTURE.md`, `docs/WORKFLOW.md`,
  `docs/carriers/DITO.md`, and this completed plan.

Verification evidence collected:

- Full backend/service suite: 635 passed; full GUI suite: 255 passed; full Node
  suite: 79 passed. Total: 969 tests, with 36 new cases versus the task baseline.
- New focused GUI coverage: 30 tests for scheduling, preferences, shared
  Home/tray data, zero/stale/expiry, tray gestures/placement, close/exit and
  instance ownership. The final full GUI run passed all 255 cases in 214.467s.
- Native Windows tray mouse checks passed for actual left open/close/reopen,
  right-click menu, Escape, popup work-area containment and horizontal fit.
  Synthetic zero appeared in both views. Closing hid the window without stopping
  its timer. Two reads were 30.04 seconds apart while hidden; Exit disposed the
  timer/session/icon. A second native run verified Open restores the window and
  visually checked the final navy card styling.
- A real separate-process local activation check passed: one owner, one
  activation from the second launch, and reacquisition after owner shutdown.
- Wheel build passed; all 63 packaged runtime entries matched source bytes.
  AST parsing passed for 101 Python files, and TOML parsing passed.
- All 24 protected router/SMS/login/SIM-page/resource baseline files matched
  their starting hashes. No new live account/router access or account capture.
- Two initial full-run failures were test synchronization issues. The existing
  demo inbox test observed an idle gap before its queued replacement read; it
  now waits for a rendered inbox and both controllers idle. The new same-process
  blocking IPC test starved its own Python accept callback; it now uses
  asynchronous delivery plus a fixed notification assertion. Production SMS
  retrieval is unchanged; real cross-process activation was separately proven.
- Tracked diff/whitespace and new-file whitespace checks passed. The final
  worktree has 29 modified tracked files and 42 untracked files, including earlier
  authorized work. Nothing is staged; no commit or push was created. This task
  modified 20 pre-existing files and added four runtime modules, five GUI test
  modules and this plan. No dependencies or separate background service added.

Limits: MyDITO still requires sign-in after process restart. The existing source
does not provide a verified total allowance, so no progress percentage is shown.
HTTP 429/Retry-After is recognized when the official client preserves its status
and headers; if that client discards them, generic bounded failure backoff is
used. Real server expiry/rate limiting was not forced during synthetic checks.

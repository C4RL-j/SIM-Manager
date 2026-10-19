# Move MyDITO account controls to Home

Scope: reuse the existing account controls, official login/OTP/session/account
services and profile binding. Move their UI ownership to Home, add a compact
disconnected prompt and connected-card Disconnect action, and remove the SIMs
account card. Preserve all balances, refresh behavior, router status, profile
creation/rename, SMS, Settings diagnostics and navigation.

- [x] Inspect current account owner, callbacks, state guards and tests.
- [x] Move Home/SIMs presentation and MainWindow wiring without service changes.
- [x] Update existing interaction tests and add focused restart/state coverage.
- [x] Run suites, native synthetic UI/resize checks, wheel/syntax/scope review.
- [x] Record changed files, results and complete this plan.

The reference image is a visual prompt example. The implementation must launch
the real existing official sign-in flow and omit the example's implementation
request disclaimer. Router connectivity remains independent from MyDITO login.
Validation uses synthetic services and isolated profile stores, without accessing
real credentials/accounts, clipboard data or changing router configuration.

## Completed behavior

Home owns the existing AccountControls and its single service listener. The
compact MyDITO Account prompt shows status, explanation and a full-width teal
Connect DITO action. Connecting preserves Show sign-in, Cancel and explicit Copy
OTP. Only the inserted DITO profile enables connection. Missing/unknown profile
and unavailable-service contexts have safe disabled explanations.

Verified connection swaps the prompt for the existing account data card, including
its pending/unavailable/stale states, actual reported values, last-successful time
and Refresh account. A small Disconnect delegates to the original control's
handler, clears account data/session and returns the prompt. Expiry/mismatch uses
the same primary action for Sign in again. Those messages survive router refresh.
Account authentication is independent from the unchanged LTE/router/SIM status.

MainWindow retains the sole guarded account/profile-state bridge. OTP inbox and
selected-message offers, session-switch cleanup, reconnect and shutdown are routed
to the same controller under Home. No second listener, browser, polling or service
was added. The redundant trailing context render was removed to preserve Home's
bound explanations. SIMs no longer creates an account control and retains its
profile list, details, creation and Rename behavior. Saved-row browsing cannot
switch the inserted SIM or cancel its sign-in.

Restart recreates a disconnected account service while retaining saved SIM
metadata. It restores neither MyDITO session nor account data and never opens the
carrier browser automatically. D2 remembered login remains independent.

## Incremental changed files

- `src/sim_manager/ui/accounts.py`
- `src/sim_manager/ui/main_window.py`
- `src/sim_manager/ui/pages/home.py`
- `src/sim_manager/ui/pages/sims.py`
- `src/sim_manager/ui/theme.py` (Home rules only)
- `tests/gui/test_accounts.py`
- `tests/gui/test_account_home.py`
- `tests/gui/test_remembered_d2_login.py`
- `tests/gui/test_sim_first.py`
- `tests/gui/test_sim_pages.py`
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/carriers/DITO.md` (current launch location only)
- `plans/completed/010-home-account-controls.md` (this plan)

## Verification

- 631 backend/service tests passed in 1.853 seconds.
- Final full GUI suite: 219 tests passed in 60.269 seconds.
- 77 Node tests passed; total 927 tests, zero failures.
- Two necessary Home integration cases added: visible sign-in/data/disconnect
  flow and restart using the exact same MemorySimProfileStore, a fresh service,
  synthetic providers and no automatic browser/session/data restoration.
- Existing rejection/cancel/expiry, refresh/stale failure, OTP/clipboard privacy,
  late callbacks, physical SIM changes and remembered D2 tests remain covered.
  Router refresh preserves expiry/mismatch prompts and disabled-context guidance.
- Native Windows source and final wheel checks passed at 1120x760 and 840x600.
  Both disconnected prompt and representative connected card fit without either
  scrollbar. Actual mouse Connect/Refresh/Disconnect exercised the real service
  state machine with a synthetic browser/account response. Rejection, account
  data delivery, stale retention, router independence and fresh-window restart
  checks passed. Inspected screenshots contain synthetic content only.
- Wheel build passed; all 57 runtime entries match final source, excluding
  tests/tools/legacy. Packaged native validation exited 0.
- All 90 Python source/test/tool files parsed; TOML and whitespace checks passed.
- All 117 other preexisting project-file hashes match the task baseline,
  including authentication, carrier/account services, models, balance calculations,
  SMS/router/storage, Settings and History. Original shared theme is unchanged.
- AST comparison confirms original Connect/Disconnect, OTP copy/clearing,
  context/listener guards, message offers and shutdown handlers are unchanged.
- Final Git status includes previous work: 24 modified tracked files, 27 untracked,
  nothing staged. No commit or push. No real account/router sign-in or personal
  credential-store access was necessary or performed for this UI relocation.

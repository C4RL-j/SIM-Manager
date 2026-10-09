# D2 router login UX

Date: 2026-10-09 (Asia/Irkutsk)

Status: Complete

Scope: D2 router admin username/password only. Preserve MyDITO authentication, existing unrelated work and the read-only legacy tree. No other task or router settings operation.

1. Add a hidden-by-default password eye toggle, opt-in Remember D2 login and explicit Forget to the router dialog. Preserve alphanumeric usernames and clear transient fields/undo history on dismissal.
2. Add a Qt-free Windows Credential Manager adapter using an application-owned, router-origin-scoped generic credential, current-user/current-computer persistence and a bounded private binary blob. No plaintext file/database fallback or MyDITO storage. Offline tests inject the backend and never access the real vault.
3. Add a D2 login service wrapper that saves only after verified successful router authentication. Guard forgetting/cancellation/shutdown against late saves or session restoration. Storage failures use fixed friendly notices and do not expose credentials.
4. Prefill remembered credentials and attempt startup sign-in once. Failed automatic sign-in shows the normal dialog without retrying. Forget deletes the credential, clears autofill and invalidates the current D2 session; expose it while connected in router information.
5. Run the full backend/service, GUI and JavaScript suites, syntax/whitespace/privacy checks, native launch and packaging checks. Verify unchanged MyDITO and legacy hashes, preserve prior uncommitted work and report incremental files, behavior, totals and Git status.

No real credentials, vault payloads, login bodies or identifiers may enter logs, errors, fixtures, docs, tool output or screenshots. Live router sign-in is not needed for these tests; use synthetic sessions and temporary app-owned synthetic vault records only if native credential validation is performed.

## Final behavior

The router dialog keeps passwords hidden by default, with an accessible eye toggle, alphanumeric usernames and an unchecked Remember control. Saved fields prefill masked. Explicit opt-in saves both fields only after strict successful router-session proof and a normalized result. The next app launch tries saved login once; failure opens the usual dialog without an automatic retry. Unchecking Remember and succeeding removes an older saved entry. Forget in the dialog or Settings removes the Windows credential, clears autofill and invalidates local D2 authorization, with no server logout or MyDITO/SMS change. Storage failures use fixed friendly notices with manual login available.

Windows storage is current-user/current-computer, nonroaming and scoped to a hashed canonical private router origin. Both fields live in the protected generic credential blob, without separate username metadata or any application file/database fallback. Authorization/MyDITO session material is not persisted. Mutable temporary buffers are wiped; Python strings are transient but cannot promise physical erasure. Native writes use a separate lock so shutdown can revoke promptly and late revoked writes are removed. Forget is disabled while status work is busy.

## Verification

Verified 2026-10-09 (Asia/Irkutsk), Python 3.13.15 and PySide6/Qt 6.11.2:

- Full suites: **560 backend/service**, **153 GUI**, **57 Node tests**, **770 total**, all passed. The backend ran with site packages disabled. Added 32 storage tests, 28 login-service tests, 17 GUI integration tests and eight net dialog cases (plus strengthened existing cases). Offline tests guard actual vault/network/browser operations and use synthetic values/providers only.
- Coverage includes masked eye toggling without clipboard/log changes, exact alphanumeric usernames, secure-adapter save/load/delete/limits/malformed inputs/privacy, strict auth proof, storage errors, one startup attempt, manual fallback, Forget from either UI, uncheck/delete, cancellation and save/Forget/shutdown races. A blocked-write test confirms prompt service close and bounded GUI shutdown before later rollback. An earlier obsolete race expectation was corrected to expect cancellation after revocation; the full final backend rerun passed.
- A new app-owned isolated native Windows Credential Manager target was absent before testing, then saved, loaded with matching in-memory fields and deleted successfully. It used generated synthetic values; neither values nor blobs were printed/retained. Existing targets were preserved and cleanup passed. No real router/carrier login was performed for this change.
- Native Windows UI construction showed the 840×600 startup size, hidden password default, show/hide toggling, unchecked Remember and a dialog fitting the available screen. Editable install and wheel build passed with zero stderr. All 44 runtime files in the 48-entry wheel match source bytes; tests/tools/legacy remain excluded.
- All 69 Python AST parses and TOML syntax passed. Privacy and tracked/untracked whitespace/diff review passed. All 40 legacy paths/hashes and 75 pre-existing project files outside the 12 approved edits match the start-of-request baseline, including all MyDITO implementation/tests/evidence and prior work outside this scope. Task 010 was not started.

## Files

Seven new files:

- `src/sim_manager/storage/__init__.py`
- `src/sim_manager/storage/windows_credentials.py`
- `src/sim_manager/services/router_login.py`
- `tests/test_windows_credentials.py`
- `tests/test_router_login_service.py`
- `tests/gui/test_remembered_d2_login.py`
- `plans/completed/001-d2-login-ux.md`

Twelve updated files:

- `src/sim_manager/app.py`
- `src/sim_manager/services/device.py`
- `src/sim_manager/ui/authentication.py`
- `src/sim_manager/ui/main_window.py`
- `src/sim_manager/ui/refresh.py`
- `src/sim_manager/ui/pages/settings.py`
- `tests/gui/test_authentication.py`
- `tests/gui/test_desktop.py`
- `AGENTS.md`
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/WORKFLOW.md`

Git remains on `main` at `b046307`, with 22 modified tracked files and 23 new files total including prior uncommitted Task 009 work. Nothing is staged, and no commit was created. This request adds seven files and changes twelve relative to its starting snapshot. The broader foundation plan remains active for deferred work.

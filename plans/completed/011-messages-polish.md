# Compact read-only Messages and owned details window

Scope: Messages presentation only in the existing PySide6 application. Replace
the large inline detail panel with a full-height sender/date/two-line-preview list
and a compact owned Qt dialog matching the supplied reference. Reuse the same
normalized inbox, refresh/controller, 20-record production limit, independent SMS
router integration and selected-message OTP signal. No WPF host/framework rebuild,
SMS write operations, persistence, new retrieval or polling.

- [x] Inspect current inbox/models/controller, UI references and constraints.
- [x] Implement compact rows and owned read-only details/copy/keyboard behavior.
- [x] Preserve lifecycle/privacy; show actual successful-refresh time and safe status.
- [x] Update necessary interaction/integration tests, run suites and native checks.
- [x] Verify package, scope/privacy/whitespace and document completed results.

Reported timestamp text does not establish a timezone. Human-readable dates may
format known structures only; unknown text remains unchanged. Known comparable
timestamps can be presented newest first; uncertain dates retain router order.
Last refresh is a real local completion time, retained on error and cleared on
SIM change/closure, never a timer-driven or fabricated timestamp. All validation
messages and screenshots are synthetic; do not access live SMS/credentials.

## Completed behavior

The list fills the available Messages area, with no inline/hidden full-message
preview editor. A plain-text row delegate draws sender/date and at most two body
preview lines, including safe wrapping/elision for long names, bodies and emoji.
Single-click selects and retains the original selected-message OTP offer signal.
Double-click or Enter opens one modeless Message Details dialog owned by the main
window. The existing app is PySide6/Qt; no WPF host or new dependency was added.

The compact dark details window shows the complete sender, reported timestamp
and read-only body, with explicit Copy Message and teal Close. Escape and normal
window close work. Copy copies the body only, never reads/clears unrelated clipboard
contents and never logs errors/content. Full content remains plain text, without
HTML/link execution. Long messages wrap and scroll without horizontal overflow.
Closing/disposal clears private dialog/model/widget references; a usable refresh,
SIM reset or app shutdown closes obsolete details. Errors/cancellation retain the
current inbox and still-valid details.

Only a usable completed read advances the aware UTC last-refreshed value, shown
in the PC's local time. Unavailable/unreadable-partial/cancelled reads retain the
last-successful time; SIM change and closure clear it. Status says Inbox loaded
from router, which describes a completed read and does not assert a continuing
router/mobile/MyDITO connection.

The UI stably sorts a window newest first only when every timestamp is recognized
unambiguous ISO, valid and mutually comparable. Mixed naive/aware, missing,
ambiguous, invalid-offset or unknown-offset timestamps retain the supplied order.
Dates are not assigned a timezone. The underlying inbox/transport order and model
timestamp text stay unchanged. The router's unverified date convention therefore
remains a limit on chronological presentation, rather than an invented ordering.

## Incremental changed files

- `src/sim_manager/ui/pages/messages.py`
- `src/sim_manager/ui/message_details.py` (new)
- `src/sim_manager/ui/theme.py` (new scoped Messages constant only)
- `tests/gui/test_messages.py`
- `tests/gui/test_app_messages.py`
- `tests/gui/test_message_details.py` (new)
- `tests/gui/test_accounts.py` (open dialog for existing full-body assertion)
- `tests/gui/test_sim_first.py` (new details/time reset assertions)
- `tests/gui/test_sim_pages.py` (new details/time reset assertions)
- `README.md`
- `docs/ARCHITECTURE.md`
- `plans/completed/011-messages-polish.md` (this plan)

## Verification

- 631 backend/service tests passed in 1.476 seconds.
- Full offscreen GUI suite: 225 tests passed in 59.874 seconds.
- 77 Node tests passed; total 933 tests, zero failures.
- Six necessary GUI cases added: four dialog lifecycle/copy/plaintext/long-content
  cases plus two row resizing/order cases. Existing tests now exercise actual
  single/double-click, Enter/Escape, empty/error/partial/cancel/refresh behavior,
  completion-time retention, OTP behavior and SIM/app cleanup.
- Native Windows source and final packaged-wheel checks passed at 1120x760 and
  840x600. A synthetic 20-message inbox fills the list without outer/horizontal
  scrolling. Double-click/Enter opens an owned read-only dialog; Escape closes it;
  explicit Copy uses a stub clipboard. Long content wraps at minimum size. Failure
  retains inbox/dialog/read-time and an actual SIM-context switch clears them.
  Exactly two synthetic provider calls exercised load and failed Refresh; opening
  or copying messages added no retrieval. Native screenshots were inspected and
  contain synthetic content only. No live account/router/SMS was accessed.
- Wheel build passed; all 58 runtime entries match final source, including the
  new dialog, excluding tests/tools/legacy. Packaged native validation exited 0.
- All 92 source/test/tool Python files parsed; TOML and whitespace checks passed.
- All 122 other preexisting project-file hashes match the task baseline. SMS
  transport/normalizer/service/controller, production 20-record limit, models,
  MainWindow integration, auth/account logic, Home/SIMs/Settings/History and
  original shared/Home style constants are unchanged.
- Final Git status includes prior authorized work: 27 modified tracked files,
  30 untracked, nothing staged. No commit or push performed.

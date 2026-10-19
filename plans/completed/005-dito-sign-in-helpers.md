# SIM number and OTP helpers in the official DITO popup

Scope: native saved-SIM selector/number copy, conservative fresh-inbox OTP watch,
and explicit Fill OTP/Copy OTP. Keep the original compact official card, styling
fallback, authentication observer, request policy and isolated session unchanged.
No automatic submission, account-data request or other task.

- [x] Read architecture, profile/inbox/auth boundaries and snapshot prior work.
- [x] Add bounded in-memory freshness/number helper behind the service boundary.
- [x] Add native current-SIM selector/copy and shared-inbox watch controls.
- [x] Observe user code requests and explicitly fill only the original SMS field.
- [x] Compose helpers without changing account authentication/session behavior.
- [x] Add minimal synthetic tests and run regression suites.
- [x] Verify rendering, privacy, cancellation, packaging and incremental scope.
- [x] Record changed files/results and complete this plan.

Freshness policy: the first complete inbox read started after a user request is
baseline-only. New content observed in later complete reads may offer a candidate;
untrusted timestamps, message order or reused IDs cannot establish freshness.
No older code is offered through the popup. An OTP already present in that first
read is conservatively ignored; the official field remains manually usable.

Completed on 2026-10-09 within this request only.

The native selector displays every saved profile's name, carrier and full number;
the inserted profile is highlighted and the rest are disabled. Copy Number is
enabled only for the current DITO profile, removes exactly one initial zero and
leaves profile metadata intact. Full current numbers remain readable with long
profile names; escaped tooltips do not interpret names as markup.

Only trusted clicks on the original active Get SMS Code span start a watch.
Countdown clicks are ignored. The helper shares the existing Messages controller
and production 20-record getter, polling every two seconds for at most five
minutes. It waits for pre-existing work, discards superseded results, and does
not start a second worker or change transport/session behavior. Partial reads,
old content with changed IDs/timestamps and distinct new candidate ambiguity do
not enable actions. Newly observed content is a likely-code heuristic, not proof
of SMS authenticity, full-inbox chronology or account binding.

Fill OTP and Copy OTP require separate user clicks. Filling writes only the
recognized original six-digit SMS field with its native setter and input/change
events; it never reads the number/password/code fields, requests authentication
or submits Sign In. Unknown structures/modes/routes or visible challenges disable
filling; original-page manual entry and existing styling fallback remain intact.
SIM changes, new documents, new requests, rejection, completion and disposal
revoke temporary state and stale callbacks. Clipboard cleanup clears only an
unchanged value copied by this helper. No private values reach logs, exception
output or application files.

Verification:

- **610 backend/service**, **191 GUI**, **69 Node** tests passed: **870 total**,
  including 26 new cases (8 service, 8 native helper, 4 browser, 6 DOM helper).
  Backend tests use `PYTHONPATH=src` with `python -S -B`; GUI tests use the
  separate offscreen suite. Node coverage includes trusted/untrusted clicks,
  countdown gating, filling during countdown, strict native field changes,
  never submitting, changed structure/challenges and private-value traps.
- Native Windows end-to-end validation used only synthetic SIMs/messages and an
  offline-only synthetic page. A real trusted Qt click started two existing
  controller reads: baseline then fresh candidate. A native Fill OTP click
  filled during countdown, preserved the number, emitted two field events,
  submitted zero times and closed cleanly. The test initially probed counters in
  the isolated world; reading only synthetic counters in their main world
  corrected the validation harness without changing production behavior.
- The real public MyDITO page was rendered with empty fields, synthetic profile
  metadata and the web view disabled to prevent interaction. At 480×612 (minimum
  420×592), the focused card/helper and original four controls, Terms/Privacy and
  Cancel were visible with no horizontal or vertical scrolling. The helper
  recognized the original field, with zero code-request events. No real OTP,
  router inbox, credentials, login or account data was used in this task.
- The wheel build passed: all 54 runtime entries match source bytes, including
  the three new runtime assets; tests/tools/legacy are excluded. All 82 Python
  files parse, TOML and new JavaScript syntax pass. Diff/whitespace and privacy
  reviews pass. All 40 legacy hashes and 100 prior project files outside the
  eight modified files match the task baseline, including the auth observer,
  auth policy, focus script, account/profile services and SMS transport.
- Native normal and DEMO startup/closure also passed with network/vault access
  guarded and normal initial loading suppressed. The production lazy factory
  receives the saved profile service and the same Messages controller; creating
  it opens no browser. The explicit DEMO launch remains synthetic.
- The [public login rendering source](https://my.dito.ph/p__Login.a8b21259.async.js)
  still separates ordinary SMS field changes
  from explicit form submission. Its send/countdown class gate is mirrored
  only by request observation; filling is permitted during countdown. No auth
  API investigation or change was needed.

Changed files for this request (15):

- `AGENTS.md`
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/WORKFLOW.md`
- `docs/carriers/DITO.md`
- `src/sim_manager/app.py`
- `src/sim_manager/carriers/dito/browser.py`
- `src/sim_manager/carriers/dito/sms_helper.js` (new)
- `src/sim_manager/services/sign_in_helpers.py` (new)
- `src/sim_manager/ui/sign_in_helpers.py` (new)
- `tests/gui/test_dito_browser.py`
- `tests/gui/test_sign_in_helpers.py` (new)
- `tests/test_dito_sms_helper.js` (new)
- `tests/test_sign_in_helpers.py` (new)
- `plans/completed/005-dito-sign-in-helpers.md` (new)

Git remains on `main`: eight modified tracked files and eleven untracked files,
including four untracked artifacts from the preceding popup work. Nothing is
staged and no commit was created. Prior work is preserved; no other task started.

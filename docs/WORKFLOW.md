# Development workflow

The repository root is `C:\PROJECTs\SIM-manager_workspace\sim-manager`. Run project commands there. Initialize Git only in this directory; never initialize Git at the workspace root or include `../old/D2-desktop/` in this repository.

The legacy tree is read-only reference material. Copy approved reusable code into `src/sim_manager/`; never import from the legacy tree at runtime. Compare before/after file lists and SHA-256 hashes when verifying that legacy files remain unchanged.

Read `AGENTS.md`, the relevant docs, and the active plan before changing code. Implement only the approved task. Tasks 001–008 and 006.1 completed the transport foundation, scoped read-only hardware/firmware discovery, carrier-neutral device state, direct D2 authentication/live status, native PySide6 shell and neutral read-only Messages with explicit demo isolation. Task 009 completed only DITO authentication/session lifecycle with controlled live account validation. Account data, carrier detection, Smart, persistence and Task 010 were deferred at that checkpoint; later separately authorized work is documented below without changing that historical evidence.

## Automatic account refresh and tray — separately authorized

Use the existing official MyDITO account reader and normalized runtime state.
Home, tray and automatic refresh must share one scheduler and in-flight service
slot; opening the tray must not create a reader, browser or additional request.
Normal mode defaults to automatic account refresh every thirty seconds, with
fifteen/thirty/sixty-second choices and an off toggle in Settings. Schedule only
for the current inserted DITO profile with a validated live account. Keep router
status and SMS reads independent; do not add periodic diagnostic/SMS retrieval,
silent login, OTP requests/filling/submission, Smart or account mutations.

Test scheduling with controlled clocks and synthetic asynchronous readers:
post-sign-in refresh without duplicates, overlap/manual coordination, interval
changes, temporary failures and exponential backoff, HTTP 429/Retry-After,
success recovery, expiry and SIM/account revision changes. Keep prior verified
values and successful timestamps stale after temporary failures; never derive
allowance totals or percentages from names or aggregate buckets. Progress stays
hidden when the normalized account model supplies no verified total.

Tray tests use fake icons and synthetic snapshots. Cover toggle/second-click,
outside-click/Escape dismissal, context-menu actions, work-area/DPI placement,
long/missing/stale values and full shutdown cleanup. Close-to-tray is explicitly
configurable and defaults on for new installs; unsupported tray availability must preserve the stored
choice while disabling hiding and explaining normal exit. Verify timers continue
while hidden only for eligible existing sessions, and explicit Exit stops timers,
disposes the local session and retains the bounded worker-join behavior.

Persist only automatic-refresh enabled, interval and close-to-tray in native
current-user Qt settings. GUI tests must inject memory stores or isolated INI
settings, never read or alter the user's real preference registry, vault or
profiles. Verify strict bad-value defaults and closed save failures without
private output. Credentials, account data, OTPs, SMS, cookies and tokens remain
outside this store; process restart still requires official MyDITO sign-in.

The module launcher uses a current-user process lock and restricted local
activation channel. Test with unique temporary lock directories/server names;
a second launch must activate the owner without creating duplicate sessions,
timers or tray icons. Only the fixed activation message may cross IPC. Run the
relevant backend/service, GUI and JavaScript suites, packaging/resource checks
and native synthetic tray/lifecycle validation. Record actual totals and any
environment limitations in the task plan; do not force live rate limits/expiry
or retain real account/SMS captures to validate this behavior.

## Windows portable releases

Use `tools/Build-Portable.ps1` with the pinned environment in
`packaging/requirements-build.txt`. Build into a fresh timestamped `dist/portable`
directory, including the actual Qt WebEngine process/resources/locales, icon,
version metadata and third-party notices. Do not publish environments, build
logs, smoke reports, discovery captures, account data or local preferences.

Run the source suites and the packaged EXE's explicit `--release-smoke REPORT`
diagnostic against synthetic memory providers and a network-blocked blank
WebEngine page. This mode bypasses production stores and instance activation;
it must not read credentials or close a user's existing session. Review the ZIP,
source/history, signing status and checksum before creating a public release.
Verify the uploaded repository/tag/assets and a downloaded checksum afterward.

Start with Windows is opt-in and available only for the frozen Windows app.
Tests inject its registry backend and must never write the user's actual Run key.
New installs keep running in the tray when closed; saved choices remain intact.

## D2 router login UX — separately authorized

The current Home account-data request separately authorizes only source-verified
read-only DITO account getters in the existing isolated session. Keep subscriber
IDs/number comparisons/signing inside the page, and export only bounded reported
display values through neutral models. Tests use synthetic client responses and
offline browser/service fakes. Run all three suites before one controlled live
sign-in/account-read cycle. User credentials/codes stay on the official page;
record only field presence/counts and closed outcomes, without live screenshots,
raw payloads, private error text or retained snapshots. Do not force expiry or
change account/router settings. Other carriers and tasks remain deferred.

The current small request authorizes only router admin password visibility, opt-in Windows Credential Manager storage, one startup sign-in attempt and Forget. Keep this distinct from the completed MyDITO task and do not start Task 010. Never write real admin fields into application files/databases, fixtures, docs, logs, exception text or tool output. The eye does not copy credentials. Backend/service/GUI tests use synthetic providers and vaults; normal GUI composition is guarded from real credential-store access during tests.

Store only after strict successful router-session proof, not merely a returned snapshot. Cover startup success/failure with no loop, alphanumeric usernames, prefill/masking, uncheck/delete, safe storage failures, Forget/cancel races and closure during a stalled write. Native vault validation may use only a new app-owned synthetic entry, first checking absence and deleting it afterward; never inspect or overwrite unrelated vault entries. No live router login is necessary for this UI/storage change. Run all backend/service, GUI and Node suites plus syntax, packaging/native launch, privacy/whitespace/diff, unchanged MyDITO and legacy hashes. Record the incremental file list and totals in the dedicated plan.

## Task 007 direct router authentication

Inspect the active public Vue login/request/interceptor source before implementing any login endpoint, request body, credential transform, token extraction or logout. Record VERIFIED / INFERRED / UNKNOWN separately. `tools/d2_auth_evidence.py` is a development-only fixed-origin public-static-source probe; it never logs in, executes JavaScript, reads browser state or exports raw source. Static request candidates alone do not verify a working protocol. The browser probe remains development-only and is never imported by the application.

The only permitted state-changing requests in Task 007 are legitimate login/session creation and optional verified logout. All status reads remain the seven reviewed GETs. No configuration/SMS/APN/network/band/PIN/Wi-Fi/password/firmware operations, credential guessing or automatic repeated authentication attempts are allowed. Runtime username/password must be entered only into the application dialog (password masked), never Codex chat, command-line arguments, environment variables, config, fixtures or logs. The password is transient; authorization remains private to D2 infrastructure and is discarded on invalidation/close. Python/Qt immutable strings cannot promise physical memory erasure.

Transport checks must cover connect/TLS/send/read cancellation and deadlines, response/header limits, redirect rejection, context-safe errors and session expiration. TLS verification remains enabled by default. The bundled public D2 certificate uses an isolated trust store only for the exact default IP origin; its verified IP SAN permits hostname verification to remain enabled. Explicit anchors for other configured private IP origins also retain hostname verification. Never globally disable certificate checking or suppress unrelated HTTPS failures. The public firmware certificate and IP SAN were recovered directly from the local D2; production never resolves smartbrosettings.net through DNS or follows redirects.

Run backend/service and GUI suites offline with synthetic credentials and response shapes first. Then connect to the D2, launch the normal native application and have the user enter the password there. Verify seven successful GETs, normalized safe fields, LIVE presentation, Refresh and closure; record partial/unavailable results honestly. Do not export raw authenticated captures, tokens, cookies or private identifiers. Session expiry may be simulated offline rather than forcing an unevidenced hardware logout. Recheck independent DEMO mode, packaging, syntax, tracked/untracked whitespace, Git diff and legacy hashes. Do not mark Task 007 complete until protocol implementation and live validation are resolved.

Task 007 final validation on 2026-10-08 (Asia/Irkutsk): **368 backend/service**, **56 GUI** and **36 JavaScript** tests passed with zero failures. The live user-entered login succeeded, followed by all seven getters and a second complete cycle through Refresh; native LIVE values and closure were verified. Wrong-password/expired-session/partial/cancellation/redaction paths use offline fakes rather than deliberate bad hardware logins or forced logout. Exact installed normal/demo CLI commands from the workspace parent, without `PYTHONPATH` or offscreen override, opened native windows and exited 0 with empty output/no owned orphans. Editable installation and wheel build passed; wheel certificate/demo bytes match source and the wheel excludes tools/tests/legacy. All 42 Python files and TOML passed syntax checks; legacy hashes, privacy and tracked/untracked whitespace/diff review passed. The environment reuses the existing PySide6/Qt 6.11.2 installation; a separate fresh isolated Qt dependency install was not required or exercised. Source evidence and firmware trust remain specific to the observed D2 build; server TTL, hardware rejection code and logout behavior remain unknown. Task 008 remains unstarted.

## Task 008 read-only Messages

Keep the existing SMS wire command in `devices/d2/router.py` unchanged. Normalize the private envelope in `devices/d2/messages.py`, expose immutable neutral messages through `services/messages.py`, and inject the provider from the application composition root. UI code handles only normalized values. HTTP login/session authorization never enters this path; Messages can work independently of Overview sign-in through the existing direct Telnet shell. Do not add shell authentication, guessed commands, paging, carrier matchers, sending, deletion, read-state writes, storage or Task 009.

The existing request reads at most three records from position zero. Preserve returned order and raw timestamp text without timezone, newest-first, unread or storage claims. Accept both object and JSON-string `data` with `ItemList`; tolerate missing fields, replacement characters, empty bodies and malformed individual entries. Exact duplicate records with IDs collapse; conflicting duplicates remain and are marked partial. An available non-partial empty inbox proves zero entries; partial empty means unreadable data and must preserve an earlier usable inbox.

Messages has its own worker, Refresh, Cancel and safe status messages. Prevent overlaps and late cancelled delivery, keep prior data on failure, and cancel both workers before the shared one-second shutdown join. Clear private widgets/models/queued results on close. The production client uses the preserved three-second connect and thirty-second response bounds, one MiB raw limit, plus a thirty-six-second overall late-result/normalization deadline. Injected non-cooperative code cannot be forcibly interrupted.

Run backend/service, separate offscreen GUI and JavaScript suites before contacting hardware. Tests/fixtures must be synthetic. Then perform only one controlled native Messages load followed by its Refresh using the local D2; validate count, list/detail consistency, responsiveness and clean closure without printing bodies, senders, message IDs, OTPs or raw responses. Do not take live SMS screenshots or persist captures. Record counts/status/schema only. The UI is allowed to display private content, but logs, exceptions, assertion failures and test artifacts are not. No HTTP password prompt is needed for this independent transport.

Packaging, exact native normal/demo launches, syntax, privacy review, tracked/untracked whitespace, Git diff and all legacy hashes remain required. The foundation plan stays active for later tasks.

Task 008 final validation on 2026-10-08 (Asia/Irkutsk): **429 backend/service tests** passed in 1.605 seconds, **84 GUI tests** in 19.941 seconds, and **36 Node tests** in 1046.1352 ms, with zero failures. The controlled native Windows run made exactly two existing local inbox getter calls, initial load and Messages Refresh, each yielding three complete messages with no issues. In-memory list/detail checks, responsive heartbeat, unchanged returned record sets, cleared widgets and clean exit 0 passed. Application stdout/stderr and log counts were zero. The SMS transport required no HTTP session/password. Validation exported only counts/status/schema and retained no raw capture or live screenshot. No send/delete/mark-read/settings command was requested; firmware-internal effects beyond the unchanged returned records are unknown. Existing-environment editable/wheel packaging and installed normal/demo native launches passed with empty output/no owned orphans. All 50 Python files, TOML and JavaScript passed syntax checks; all 40 legacy hashes and 53 pre-existing project files outside the ten approved changes matched baseline. Privacy and tracked/untracked whitespace/diff review passed. Git has ten modified tracked files and eight new files, nothing staged, no commit created. Task 008 is complete; Task 009 remains unstarted.

## Task 009 DITO authentication/session lifecycle

Audit the read-only legacy reference and current official MyDITO public bundles before implementing authentication. Classify source facts, inferences, obsolete behavior and unsafe reuse separately. Source offsets/hashes belong in the sanitized DITO evidence ledger; credentials, live response bodies, session material and SMS must never become fixtures. Keep origin/request/response interpretation inside `carriers/dito/`, neutral account states/lifecycle in services, and compact injected controls in Settings.

Explicit Connect opens an unnamed off-record Qt WebEngine profile for the exact official HTTPS origin. Credentials, CAPTCHA, consent and sign-in SMS requests remain user actions on the official page. Do not inspect inputs, export cookies/storage/tokens, use the normal browser, bypass challenges or automatically submit OTPs. Restrict requests to reviewed authentication/bootstrap/legal paths and assets; block subscriber/account APIs, protected account-view scripts and external telemetry. Connected requires strict successful login response evidence followed by the site's exact success transition. No URL-only guess or fixed server lifetime is permitted.

Existing user-loaded neutral Messages can offer a likely DITO code only through the carrier adapter. Distinct matching codes are ambiguous; an explicit message selection can narrow the candidate. Copy requires a click, with paste and submission left to the user. Never log codes or infer freshness/account binding from unverified router timestamps. To make recently received OTPs reachable, production Messages requests up to 20 records through the existing getter's validated count parameter. The raw transport and standalone client's default remain three; this is a bounded window, with no paging or verified newest-first order. A controlled 100-record request failed malformed-response normalization; 20 returned complete records. Preserve deadlines, cancellation, wire cap and all no-write restrictions.

Cancel/Disconnect/shutdown invalidate generations before disposing the page/profile and temporary OTP. Disconnect is local session disposal, without remote logout/revocation claims. Rejected login remains open for manual retry. Expiry is reported only from observed authentication failure; root/new-document navigation conservatively disconnects. Restart requires sign-in. No persistence or automatic reconnect loop is authorized.

Run standard-library backend/service, separate offscreen GUI and synthetic Node observer tests before controlled sign-in. Ask the user only to complete the official window; never request credentials/codes in chat. Record closed states, counts, responsiveness, local Disconnect and profile disposal only. Do not retain live screenshots/raw captures. Then verify installed native normal/demo launches, wheel contents, syntax, tracked/untracked whitespace, diff/privacy and all legacy hashes. Do not mark Task 009 complete while legitimate sign-in/live validation is unresolved.

Task 009 final verification on 2026-10-08 (Asia/Irkutsk): **500 backend/service**, **128 GUI** and **57 Node tests** passed (685 total). The final controlled single-window official sign-in reached Connected/validated login, followed by the explicit local Disconnect button returning Not connected; profile disposal, UI responsiveness and exit 0 passed, with zero application log records/private stderr bytes. Only closed states/counts were emitted: 12 allowed auth/bootstrap, two blocked non-auth API attempts, 15 blocked external requests. No balances/promos/allowances or private material was retrieved/exported. Earlier user cancellation and a separate normal app window were resolved by this final run; no bad-password/forced-expiry/server-logout experiment was performed. Native Messages load/Refresh each showed 20 complete records without private output/captures. Editable/wheel packaging, exact installed normal/demo native launches, 63 Python AST/TOML/JSON/four-JavaScript syntax checks, legacy hashes, privacy and tracked/untracked whitespace/diff review passed. The 45-entry wheel's 41 runtime files match source. All 40 legacy files and 53 pre-existing files outside approved changes are unchanged. Git on main: 18 modified tracked files, 16 new files, nothing staged, no commit created. Task 009 is complete; Task 010 has not begun. The foundation plan remains active for future work.

## SIM-first refactor verification

Use normalized synthetic SIM observations and memory stores for GUI/service
tests. Verify UUID identity, validated ICCID fingerprint matching, same-number
distinct SIMs, unknown-profile creation, renaming and metadata reload without
active/account sessions. No new device endpoint or carrier-detection claim is
allowed. Full numbers may be shown in normal profile UI; repr, errors, logs and
test artifacts remain private.

Verify all five navigation pages, Home network/signal details, active-only DITO
controls, independent Messages and explicit inbox ownership. Switching SIMs must
dispose the old account/OTP context and reject old inbox/account callbacks.
Router authentication/status failures alone preserve the last observed profile.
Profile metadata is DPAPI-protected outside the repository; demo/injected apps
must never read real saved profiles. A synthetic native DPAPI roundtrip must use
an isolated temporary location and leave existing application storage untouched.

Run backend, GUI and JavaScript suites, native normal/demo composition, wheel
contents, syntax, privacy, diff/whitespace and legacy integrity. Record results
in the dedicated SIM-first plan. History is only a placeholder; Smart support,
account-data retrieval and Task 12 remain outside this refactor.

## MyDITO popup presentation checks

The separately authorized Home dashboard simplification keeps SIMs, Messages,
History, authentication and retrieval unchanged. Verify data/promo prominence,
the three-cell network-evidence strip, load-versus-promo expiry separation,
collapsed Settings diagnostics retaining every normalized field and no new I/O on
disclosure. Run source/backend, GUI and Node regression suites, then native
synthetic layouts at normal/minimum size, long content, missing data and expanded
details. Never capture live account/profile/SMS content for visual checks. Check
for horizontal overflow instead of merely hiding scrollbars. Account refresh,
stale/failure/expiry handling and all existing monitor values must remain covered.

MyDITO popup styling is tested with synthetic layout/control structures and the
existing fake WebEngine boundary. Check original node preservation, unknown-page
fallback, visible challenge/consent fallback, route/origin guards and cancellation.
Do not inspect auth APIs or credential/OTP values for a presentation change.
Public-page visual validation must use a fresh unauthenticated profile without
user input; never retain screenshots of populated login fields or sessions.

SIM/OTP helper verification uses synthetic saved profiles, inboxes and clipboard
objects. Cover one-zero formatting, baseline/ambiguity/expiry, shared-worker read
ownership, disabled spare profiles, explicit fill, old-document/request callbacks
and private error handling. Only the current helper request authorizes filling
the original OTP input; no automatic submission or auth API investigation.
Native input-event tests may use an offline synthetic DOM with external requests
blocked. Public-page checks remain fresh/empty, with only synthetic profile
metadata and no real SMS request, OTP entry or credentials. Keep existing styling
and auth policy/session behavior unchanged and record incremental file hashes.

## Offline transport tests


Use Python 3.11 or later. The transport has no runtime dependencies, and its tests use only the standard library. No package installation, GUI/browser package, or router connection is needed:

```powershell
# Working directory: sim-manager
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -S -B -m unittest discover -s tests -v
```

The characterization/regression suite uses synthetic socket responses and controlled clocks. It must never open a live connection. `-B` prevents bytecode files during verification. Hardware probing and browser/account work are outside Task 002. Regression cases must distinguish intentional changes from preserved legacy behavior, including echo-disabled completion, Telnet fragmentation, bounded output, cancellation, disconnects, and sanitized errors. Keep coverage for trailing bytes after the completion line, malformed outer envelopes, and wrapper traversal that stops at response envelopes.

Task 002 verification passed 78 tests on Python 3.13.15 with site packages disabled using `python -S -B -m unittest discover -s tests -v`. Keep the 0.5-second idle wait for banner/wake-up reads within their 0.7/0.25-second phase deadlines; receive polls of up to 0.1 seconds when cancellation is enabled must not shorten that idle wait.

Task 003 verification passed 139 tests on the same interpreter with site packages disabled: the original 78 transport tests plus 61 discovery tests. The production transport and original tests were unchanged. Discovery tests cover the fixed query registry, fragmented framing, cancellation/deadlines/cleanup, privacy summaries, raw-capture confinement, and inert manual invocation.

Run the browser development probe's separate offline JavaScript tests with Node's built-in runner:

```powershell
node --test tests/test_d2_browser_probe.js
```

No npm dependencies or live router/browser are required. Python transport/discovery tests remain standard-library tests and do not depend on Node or run the JavaScript suite.

Task 004 verification passed 190 Python tests in 0.974 seconds and 36 Node tests in 693.5684 ms; `node --check tools/d2_browser_probe.js` also passed. Coverage includes the supplied sanitized authenticated-report fixture and explicitly synthetic hidden values. Two earlier development-summary expectations changed with an intentional privacy tightening and a new privacy regression; the original 78 transport tests and production package remain unchanged. The capability report records source provenance, initial unauthenticated checks, and seven successful authenticated GET observations from the signed-in Brave tab.

## Review and privacy

Run the relevant offline suite, review `git diff` and `git status`, and verify the legacy hashes before reporting completion. Include newly created files in the review; ordinary `git diff` does not show untracked file contents. Do not commit unless explicitly requested.

Diagnostic logs and exception output must mask or omit full phone numbers/MSISDNs, IMSIs, ICCIDs, IMEIs, IP/DNS addresses, APNs, OTPs, sensitive SMS bodies, authentication cookies, Authorization values, tokens, and passwords. Do not retain real messages, account data, or credentials in tests or fixtures. Device-state repr/str must omit all fields; explicit serialization needs its own privacy review.

## Task 003 hardware discovery

Use `tools/d2_discovery.py` only through explicit manual invocation. `--list-queries` is offline; `--query` contacts hardware using a fixed reviewed read-only command. Method/schema names alone do not establish safe execution. Find firmware/legacy evidence before adding or calling a vendor getter. Do not guess AT commands, read SMS merely for discovery, modify APN/PDP/network/band/SIM/configuration state, restart services, reconnect data, reboot, or install router software.

The default query deadline is 8 seconds, with a 256 KiB raw-wire cap per read phase and Ctrl+C cooperative cancellation. Normal output allows only reviewed metadata and omits unknown values; parse/error fallback must never dump raw text. Raw output requires the explicit `--capture-raw` flag and is confined to the ignored `artifacts/d2-private/` directory. Keep that directory untracked and do not use its contents as shared fixtures.

Record exact executed commands, their read-only basis, exit status, source/path, masked response shape, observed fields, units, and firmware assumptions in `docs/devices/D2-HARDWARE-CAPABILITIES.md`. Use VERIFIED, INFERRED, NOT FOUND, and UNTESTED per field. Missing evidence, failed access, and privacy-omitted values do not establish absent capabilities. Keep operator/PLMN evidence neutral and separate from later carrier interpretation.

Run all offline transport and discovery/parser tests, review diff/whitespace, verify unchanged legacy paths/hashes, and check that no raw captures are tracked. Document the actual manual hardware queries and confirm they contain no router setting changes.

## Task 004 cellular telemetry discovery

Inspect the router's firmware/web assets for actual request construction and response fields before invoking any candidate. Where practical, observe requests generated by status pages through an existing legitimate local admin session. Do not interact with configuration controls, store/log the router password, or expose cookies/tokens. Only extend the fixed discovery allowlist after evidence establishes a read operation; no arbitrary shell/UBus/CGI/RPC/AT interface is permitted.

For each candidate record source/page/path, exact request/method, read-only basis, authentication requirements, response shape, observed fields, state-change observation, and classification. A field name or getter-like name alone is insufficient. If safety is unresolved, leave the candidate untested and explicitly describe its safety as unverified. Never execute set/save/apply/update/modify/connect/disconnect/restart/reset/reboot/SMS-send/SMS-delete/APN/RAT/band/PIN operations or modem commands with unknown side effects.

Use only sanitized observed shapes for offline fixtures. Test missing/null fields, unexpected types, partial/malformed responses, observed firmware variations, and sensitive-value redaction without hardware. Keep runtime observations separate from inferred units/status semantics. PLMN/operator values remain neutral evidence; no carrier mapping or production detection is authorized. If no safe getter is found, document that limit without inventing a fallback.

If the legitimate session is available only in Brave, `python -S -B tools/d2_discovery.py --browser-script` prints the fixed `tools/d2_browser_probe.js` offline. Manual execution in the already signed-in local HTTPS admin tab sends only the seven evidenced GETs. The source-confirmed `localStorage.Authorization` value becomes an Authorization header inside that same origin; cookies/tokens are never exported, pasted into this environment, or written to files. Do not dump browser storage or attach raw network responses.

The browser probe accepts only its fixed local router origins, rejects redirects, requests no storage/configuration writes, and supports `SIM_MANAGER_D2_PROBE.cancel()`. Its total deadline is 20 seconds with a 256 KiB limit per response. Share only the sanitized report: identifiers, addresses, APN, and cell IDs masked; arbitrary operator/model/version/unknown strings omitted; narrowly allowed enums/bands/signals and neutral PLMN strings retained without interpretation. Source-confirmed field keys become runtime evidence only when actually observed.

Task 004's received report has seven HTTP/body-code-200 object responses and 49 typed fields. It verifies raw Ready/Connected/LTE labels, band/signal strings, and identifier field presence/types. Masks hide empty strings as well as populated ones; do not claim valid/non-empty identifiers or cellular addresses. PCI and PIN-retry values remain omitted strings. `wirelessinfo` exported no allowlisted fields, which does not prove empty raw data. Actual operator/PLMN, registration/roaming, APN/PDP, radio units, modem firmware revision, absent/locked SIM states, and other firmware variants remain unverified. Only two endpoints were separately checked unauthenticated and returned 401; the other five used the session without isolated authentication-requirement tests. GET-only `state_changes_requested=false` records requested operations, not an audit of firmware-internal side effects.

Task 004 verification ran all offline tests plus its new parser/discovery tests, verified legacy hashes and unchanged production transport behavior, and checked for router-setting requests, tracked captures, and diff/whitespace. Task 005 was unstarted at that historical verification point.

Update the active plan with results and limitations. Keep the foundation plan under `plans/active/` while later foundation tasks remain outstanding; finishing Task 004 does not finish the whole plan.

## Task 005 normalized device state

Work only in the Device and carrier-neutral model boundary. Keep raw D2 response objects inside the parser/client. Use the sanitized Task 004 report as observed-shape evidence; reconstruct hidden values only from explicitly synthetic data. Do not invent units, carrier identity, registration/roaming, SIM presence/locked states, or valid/non-empty identifiers from masked field types. Document VERIFIED RAW VALUE, NORMALIZED REPRESENTATION, and INFERRED/UNKNOWN SEMANTICS separately.

The status client requires an explicitly injected authenticated-session implementation for retrieval. The production package has no Brave bridge and must not import the development browser probe, extract Authorization material, prompt for/store credentials, or open hardware by default. A missing session returns authentication-required unknown state without I/O. An injected session must honor the shared monotonic deadline, cooperative cancellation, and per-response cap; tests use fake sessions and controlled time, not the browser/router.

Verify optional/missing/null/empty/malformed/future fields, band/signal mapping, Ready/LTE/Connected labels, partial endpoint failures, neutral unknown carrier evidence, availability without identifier/address storage, opaque repr/log output, and safe closed error codes. Run both full offline suites, retain all prior transport tests, compare legacy/transport/fixture hashes, and review tracked/untracked diffs and privacy.

Task 005 verification passed **260 Python tests** in 1.888 seconds on Python 3.13.15 with `PYTHONPATH=src` and `python -S -B -m unittest discover -s tests -v`: 190 unchanged prior tests, 31 parser/model cases, and 39 client cases. The unchanged JavaScript suite passed **36 tests** in 688.2856 ms; `node --check tools/d2_browser_probe.js` passed. Tests verify response-limit contract forwarding, not independent raw HTTP cap enforcement. All 40 legacy paths/hashes and 19 pre-existing non-document project files matched the Task 005 baseline, including the SMS transport, original transport tests, development tools/tests/fixtures, package initializers/metadata, and ignore rules. No new hardware/browser access or router-setting changes occurred. Syntax, privacy, and tracked/untracked diff/whitespace checks passed; no real identifier or credential values were introduced. At that historical verification point, `main` had six modified documentation files and five untracked source/test files, an unstaged normal index, and no Task 005 commit. Task 005 is complete within its boundary scope; the authenticated-session implementation remains future work. Task 006 was unstarted then; the foundation plan stays active.

## Task 006 native desktop shell

Use PySide6 Qt Widgets for the approved Windows shell, with Overview, Messages, and Settings only. The UI consumes the existing `DeviceState` through service/presentation interfaces. Keep fixed safe labels, optional unit-neutral signals, Carrier Unknown, and availability values; never display identifiers, arbitrary model/operator text, raw payloads, or raw exceptions. Messages remains an unconnected shell; Settings is read-only without persistence or credentials.

Default production mode must launch and refresh without a router/browser connection, showing authentication-required unknown state. Explicit `--demo` selects sanitized Task 004 fixture-derived state and must keep DEMO visible. Never silently switch a failed production request to fixtures. No automatic browser, carrier web login, runtime Brave bridge, settings writes, or Task 007 is authorized.

Run refresh in one cooperative Python daemon worker with Event/Queue communication and Qt main-thread timer polling; never mutate widgets from the worker. Block overlapping refreshes. On close, cancel, stop polling, discard late results, and bounded-join the worker. Shipped providers must terminate cleanly; arbitrary injected providers that ignore cancellation cannot be killed forcibly. Their daemon status only prevents process-shutdown blocking.

Keep backend/service tests standard-library-only and GUI tests separate with the desktop dependency installed. Maintain offscreen construction/rendering, missing/partial/demo/authentication/error/privacy, asynchronous refresh/overlap/cancellation, resize, and shutdown coverage. Do not contact hardware or use real browser authentication for this visual milestone. Verify unchanged legacy/backend files, no sensitive additions, and tracked/untracked diff/whitespace. At Task 006 completion, Task 007 had not begun; its later verification is recorded above.

Install the native desktop extra and launch from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[desktop]"
.\.venv\Scripts\python.exe -m sim_manager
# Explicit offline fixture mode:
.\.venv\Scripts\python.exe -m sim_manager --demo
```

`desktop` declares `PySide6-Essentials>=6.8,<7`; base/backend runtime dependencies remain empty. Backend/service tests use `PYTHONPATH=src` and `python -S -B -m unittest discover -s tests -v` without Qt. GUI tests require site packages and are deliberately isolated under `tests/gui/`, which has no `__init__.py`:

```powershell
$env:PYTHONPATH = (Resolve-Path ./src).Path
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/gui -v
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
```

The platform override is for tests only; clear it before native visual checks. Verify both production Authentication required and explicitly marked DEMO windows, resize at the minimum size, page navigation, Refresh loading/overlap behavior, and clean closure. The separate Node test/syntax commands remain applicable. Record actual environment versions, full test counts, native launch/visual evidence, and any lifecycle limits after root verification; do not replace historical Task 005 totals with interim Task 006 runs.

Task 006 final suites on Python 3.13.15 and PySide6/Qt 6.11.2 passed: **285 backend/service tests** in 2.150 seconds (260 unchanged prior cases plus 25 service/presentation/demo cases), **30 offscreen GUI tests** in 5.092 seconds, and **36 Node tests** in 459.8918 ms. JavaScript syntax also passed. Native Windows-platform production/demo construction, show, refresh, and close checks passed; screenshots were visually inspected for readable fonts and content fit at 1120×760, and no refresh workers remained. Repeated shutdown is non-blocking after the first bounded join.

Packaging verification reused the preinstalled Qt in an ignored local environment created with `python -m venv --system-site-packages .venv`; the clean-environment install instructions above remain the normal workflow. `.venv/Scripts/python -m pip install -e ".[desktop]"` succeeded. Both installed `python -B -m sim_manager` and `--demo` launched native windows from the workspace parent with `PYTHONPATH` removed, then closed with exit code 0 and no stdout/stderr or orphan workers/processes. `python -m pip wheel . --no-deps --wheel-dir dist` succeeded; the wheel contains the entry/UI/services and exact sanitized demo resource and excludes tests/legacy code. Fresh fully isolated dependency installation was not separately exercised.

All 40 legacy paths/SHA-256 hashes and 27 pre-existing project files outside the approved documentation/metadata edits remain unchanged. AST/TOML syntax, privacy, tracked/untracked diff/whitespace, and resource-copy checks passed; no private captures or staged changes exist. UI imports contain no D2 device/development/browser modules and no endpoint/localStorage references. All eighteen new files contain no seven-or-more-digit text values. With Qt unavailable under `-S`, normal startup returns only a friendly installation instruction with exit code 1; `--help` still works without Qt. Git is on `main` with seven modified files (six docs and `pyproject.toml`) and eighteen untracked files (17 Python and one JSON). No Task 006 commit was made; `.venv/`, build outputs, distribution files, and egg-info remain ignored. No router/browser access or setting change occurred. Task 007 remains unstarted.

# SIM Manager

A lightweight Windows SIM management application in development. The native PySide6 desktop shell provides Home, SIMs, Messages, a History placeholder and Settings. It manages saved SIM profiles while preserving direct local D2 authentication/status, the read-only inbox and isolated MyDITO authentication. Python 3.11 or newer is required.

## SIM profiles and navigation

Home shows the active SIM's name, full number and carrier label alongside the
existing network, signal and connection status. Open Messages is a quick inbox
action. Load, data, promo and expiry show Not available until a carrier service
supplies those values; this refactor adds no account-data requests.

SIMs lists saved profiles and marks the inserted SIM Active. A known validated
router identity selects its saved profile automatically. An unknown SIM offers
Create profile with a custom name, optional number and Unknown/DITO carrier
label. Carrier is a user choice, not automatic detection. Select a saved profile
to view it or Rename it; selecting a row does not change the inserted SIM.

Each profile has an independent UUID. Automatic matching uses a domain-separated
fingerprint of a conservatively validated router-reported ICCID, never a phone
number. Raw ICCIDs and IMSIs are not retained. If identity cannot be validated,
a profile can be current for that continuous observation but will not match
automatically after removal or restart. Authentication/transport failures retain
the last observed binding; they provide no evidence of a SIM replacement.

Profile metadata is saved outside the repository at
`%LOCALAPPDATA%\SIM Manager\sim-profiles.dpapi`, encrypted with current-user
Windows DPAPI and replaced atomically. It contains names, optional numbers,
carrier choices, UUIDs and identity fingerprints only. Active state, MyDITO
sessions, router credentials and messages are excluded. DEMO and injected
providers use isolated memory stores. Damaged/unavailable storage fails safely.

DITO Account controls belong to the active DITO profile in SIMs. Sign-in,
Disconnect and explicit Copy OTP retain their existing behavior. Changing SIMs
disposes the old account session and clears its OTP/inbox; returning to a profile
requires explicit Connect again. Messages remains an independent sidebar page
and names its SIM context. Settings contains router and application information,
including Forget saved D2 login. History is a placeholder; Smart support and
Task 12 remain unstarted. The refactor passed 836 tests plus native Windows,
DPAPI and packaging checks; the [completed plan](plans/completed/002-sim-first-refactor.md)
records the file inventory, verification and recognition limits.

Task 007 adds direct router authentication and LIVE status without a browser. Start normal mode, choose **Sign in**, and enter the router username and masked password in SIM Manager. The username accepts letters and numbers; without a remembered login, both fields start blank because the firmware has no verified default username. Credentials stay transient unless you explicitly select Remember D2 login, which stores both fields with Windows Credential Manager protection after successful router authentication. Successful sign-in automatically retrieves the seven verified status getters; **Refresh** reads them again. LIVE marks real snapshots; explicit `--demo` remains independent and permanently marked DEMO. Live hardware validation passed: legitimate login, all seven getters, complete normalized state, LIVE GUI display, Refresh and clean shutdown.

The application connects directly to `https://192.168.1.1`, performs no DNS lookup, and rejects redirects. It trusts only the bundled public D2 certificate for that exact default origin, with certificate and IP hostname verification enabled. The observed certificate is valid through 2030-10-26. Other configured private IP origins use ordinary verified TLS unless an explicit certificate is supplied. Certificate replacement requires a reviewed resource update; there is no insecure fallback.

The verified firmware protocol is `POST /web/v1/user/login` with JSON `{username, password}` and no credential transformation. A successful `{code: 200, data: {Authorization: ...}}` creates a private in-memory session; subsequent approved GETs send that opaque value verbatim in the Authorization header. No browser, DevTools, localStorage, cookies or manually copied tokens are required by the implementation. HTTP/body 401 or 403 invalidates the session, stops that refresh cycle and offers Sign in again. Remembered D2 credentials get one startup login attempt; failure opens the usual masked sign-in dialog without retrying automatically. Router Authorization is never persisted. Closing cancels work and discards authorization; the source-evidenced logout POST is deliberately unused.

Login has a 20-second deadline; the subsequent seven-getter refresh has one separate 20-second deadline and 256 KiB per-response limit. Both use one cancellable worker, and GUI shutdown joins for at most one second. Safe UI messages distinguish authentication required/rejected, unreachable router, connection/TLS trouble, malformed data and partial status. Carrier stays Unknown; signal units, registration and roaming remain unverified.

Open **Messages** to load up to 20 messages through the preserved local D2 Telnet/UBus getter. Task 009 expands the production service's request window so a likely sign-in OTP outside the earlier three-record window can be shown. Select a row to view its complete plain-text content. Messages has its own **Refresh** and **Cancel** actions, independent of Overview and its HTTP admin session. Failed or cancelled reads keep the displayed inbox; malformed individual entries produce a partial warning without discarding readable messages. An unreadable partial response cannot establish that a previously displayed inbox is empty.

SMS content and sender identifiers appear only in the requested Messages view, remain in memory, and are never written to application logs or diagnostic errors. Private message models have opaque repr/str output; closing clears the visible content and cancels both read workers within one shared one-second join budget. Explicit `--demo` uses synthetic messages, keeps DEMO visible, and never replaces failed live reads with demo data. Sending, deletion, mark-read actions, message persistence, carrier OTP/account integration, and Task 009 are outside Task 008.

## D2 router login controls

D2 sign-in uses the router administrator username/password, separately from MyDITO. The password starts hidden; the eye toggles visibility without logging or copying it. **Remember D2 login** is unchecked by default. A successful login can save both fields in the current Windows user's Credential Manager on this PC, scoped to the router origin. No JSON, SQLite, plaintext file or fallback storage is used; router Authorization and MyDITO cookies/tokens are never stored there.

On the next launch, the app attempts remembered D2 login once. If it fails, the normal dialog opens with masked saved fields for correction; there is no retry loop. Opening Sign in also prefills saved fields. **Forget saved login** appears in Settings's Router information and the saved-login dialog; it deletes the Windows entry, clears autofill and invalidates local D2 authorization. Unchecking Remember and successfully signing in removes the previous saved entry. Storage failures produce fixed notices and retain manual sign-in. DEMO and injected offline providers never access the real vault. MyDITO authentication is unchanged.

This UX passed 560 backend/service, 153 GUI and 57 Node tests (770 total), an isolated synthetic native vault save/load/delete check, native Windows dialog launch, packaging, syntax, privacy and integrity checks. The [completed D2 login plan](plans/completed/001-d2-login-ux.md) records the file inventory and results.

## First desktop milestone

The native Qt Widgets shell started as a visual milestone. Overview displays safe SIM/network/signal/WAN state with unknown values left explicit and Carrier Unknown. Messages consumes a normalized message service rather than raw SMS transport responses. Settings contains read-only router-address/status information, app information and a local Forget saved login action. SIMs contains the Task 009 DITO account controls for its active DITO profile. D2 credentials may be remembered securely by explicit choice; profile metadata is saved separately and MyDITO sessions remain unpersisted.

The app opens at its compact 840×600 window size and can be resized or maximized.

Without remembered D2 credentials, normal mode initially reports Authentication required without network I/O. Explicit Sign in creates a direct router session and refreshes live status; no browser opens. Explicit `--demo` uses sanitized Task 004 fixture-derived state and labels the UI DEMO. Demo is never substituted silently for live data. The existing snapshot model is named `DeviceState`; no backend rename to the conceptual `DeviceSnapshot` is required.

Overview and Messages Refresh use their service interfaces outside the GUI thread, block overlapping requests for each page, and report safe loading/error states. Closing requests cooperative cancellation and worker joins within one shared second; repeated shutdown is non-blocking. Shipped production/demo providers are bounded; arbitrary injected providers that ignore cancellation cannot be forcibly stopped, though daemon workers cannot block process shutdown. DITO balances, promos and allowances, Smart account integration, carrier detection, tray behavior, charts, configuration storage and Task 010 remain deferred.

Task 006.1 polished the existing UI: compact routine status, warnings/errors as banners, prominent Carrier Unknown/Network/SIM information, all six signal fields, compact connection details, and small monochrome navigation icons. At that milestone, Refresh appeared only on Overview and Messages remained unconnected. Overview Cancel remains available on any page while status work is running; Task 008 adds separate Messages actions. The DEMO badge and offline-fixture disclosure persist across every page. Settings groups read-only router and application information.

## DITO account authentication — Task 009

Open **SIMs → active DITO profile → DITO Account → Connect DITO** to open the official `https://my.dito.ph/` sign-in page in SIM Manager's isolated Qt WebEngine window. Enter the account details, CAPTCHA and OTP directly on that page and complete any required consent there. SIM Manager supplies no credentials and bypasses no challenge. The browser module and network activity start only after Connect; application startup, router Sign in and demo mode do not open the carrier browser.

The authentication observer accepts only a successful official login response with strict `loginSuccess: true`, followed by navigation to the exact `/pto/home` route after the site's session/consent flow. A route alone cannot establish Connected. A request allowlist permits the official authentication and consent flow plus first-party authentication assets; subscriber details, balances, allowances, promos, purchases, password reset and external telemetry are blocked. The protected BaseLayout and Home script families are also blocked to prevent account bootstrap and subscriber-detail guards after the authentication milestone. The account website view is outside this task; the isolated browser retains only its in-memory session. Public source provenance, hashes, closed live outcomes and remaining unknowns are recorded in the [authentication evidence ledger](tests/fixtures/dito/auth-source-evidence.json) and [DITO documentation](docs/carriers/DITO.md). Controlled live sign-in confirmed this restricted authentication-only handoff.

The active DITO profile shows Not connected, Sign in with DITO, Connected, Session expired or a friendly error. Rejected sign-in stays open for a manual retry. **Show sign-in** raises the existing window without another login attempt. **Cancel**, **Disconnect** and application shutdown revoke callbacks, clear the temporary OTP and dispose of the local browser context. Disconnect clears this application's isolated session; it does not claim server logout or remote token revocation. An observed authentication failure can mark expiry; returning to the sign-in page conservatively disconnects, including full document navigation. No session lifetime is assumed and no automatic login loop runs.

Messages remains carrier-neutral. While sign-in is open, an existing inbox load or user **Refresh** can offer one unambiguous likely DITO OTP to the carrier adapter. If the inbox contains conflicting likely codes, select the intended SMS to narrow the candidate to that message. **Copy OTP** appears only after a match and requires a click; paste and submit on the official page yourself. There is no extra SMS polling, automatic fill or automatic submission. The historical sender/phrase rule does not verify freshness, router timezone or account ownership. Codes never appear in diagnostics or account labels. A copied code is cleared from the clipboard when its state ends or the app closes, if the clipboard still contains that code.

Controlled D2 reads during Task 009 returned a safe `malformed_response` outcome for a 100-record request and 20 complete messages for the chosen 20-record request. A likely OTP was present beyond the first three returned records; no code, sender, body or identifier was exported. Native Messages load and Refresh both displayed 20 complete records. These counts verify the current retrieval window, not chronological ordering or code freshness. The separate official sign-in/session check passed.

The unnamed off-record profile uses memory-only cookies and cache. Passwords, OTPs and raw session material are never written to application config, logs or fixtures. SIM Manager does not extract browser cookies/tokens or read the user's normal browser profile; restarting requires sign-in again. Demo account connection changes explicitly marked synthetic states only, without a browser, credentials, network or OTPs. Task 009 implements authentication only; it does not retrieve account balances, promos or allowances.

## Install and launch on Windows

From the `sim-manager` repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[desktop]"
.\.venv\Scripts\python.exe -m sim_manager
```

For explicit offline demo mode:

```powershell
.\.venv\Scripts\python.exe -m sim_manager --demo
```

The `desktop` extra installs `PySide6-Essentials>=6.8,<7` for the native Qt Widgets shell and `PySide6-Addons>=6.8,<7` for the optional DITO WebEngine surface. Base/backend imports have no runtime dependency on Qt. Production launch offers Sign in for direct router authentication; `--demo` displays sanitized fixture-derived values with a DEMO indicator. The carrier browser opens only after Connect DITO in normal mode. No router settings are modified. Use a normal Windows desktop session for launch; the offscreen setting below is only for GUI tests.

## Current scope

The D2 SMS transport is `sim_manager.devices.d2.router`, originally copied from the read-only legacy reference at `../old/D2-desktop/router.py`. It uses the existing Telnet/UBus inbox path. The default `192.168.1.1:2323` endpoint, default three-record request, exact UBus command, and fixed historical marker remain unchanged. The standalone `D2MessageClient` also defaults to three records; Task 009's production `LiveMessageService` supplies the existing getter's `ReadNum=20` parameter. No new transport command or paging API is introduced.

The transport now preserves Telnet state across reads, recognizes a terminated standalone completion-marker line with command echo enabled or disabled, bounds raw received bytes, uses monotonic deadlines, supports cooperative cancellation, and emits generic errors without raw exception chains. Marker text inside command echoes or JSON strings cannot complete a read. Response processing stops at the marker line; trailing JSON or Telnet bytes in the same receive are ignored.

`fetch_sms_response` keeps its five existing positional parameters and adds keyword-only `stop_event` and `max_response_bytes`. An optional event with `is_set()` requests cancellation, reported as `RouterCancelledError`. The default byte limit is 1 MiB per read phase (banner, wake-up, command response), including Telnet control bytes. EOF or a reset raises `RouterDisconnectedError`, a subclass of `RouterConnectionError`.

The transport still returns raw SMS envelopes. Stringified or otherwise loosely shaped `data` is preserved, and the last successful outer envelope can still win over a later error envelope. Response selection prevents nested SMS objects from overriding valid or malformed outer envelopes. Transparent-wrapper fallback remains when no top-level envelope exists; traversal stops at any dictionary containing both `code` and `msg`, including error envelopes. The public JSON extraction helper still enumerates nested objects. Task 008 adds `devices/d2/messages.py` above this unchanged transport: it validates the selected envelope and object/JSON-string `data.ItemList`, then creates carrier-neutral `Message` and `MessageInbox` values for `LiveMessageService` and the UI.

The optional normalized fields are message identity (`SmsId`), sender (`number`), raw router date/time text (`smsdate`/`smstime`), and body (`content`). Missing or malformed fields remain usable where possible; unsupported envelopes fail safely. Exact duplicate-ID rows collapse, conflicting duplicate-ID rows remain, and router order is preserved. The production 20-record window is not full-inbox paging or a verified newest-first order. Timestamp timezone, ID uniqueness, `readed` meaning, storage metadata, other firmware shapes, and non-UTF-8 modem encodings remain unverified. No read/unread or storage meaning is invented. SMS requests retain the 3-second connection limit, 30-second response limit, and 1 MiB per-phase wire cap; the normalized client rejects results after its 36-second deadline and honors cooperative cancellation.

Task 005 adds the normalized Device boundary: immutable SIM, network, radio, WAN, carrier-evidence, snapshot, and partial-error models; a D2 parser; and one aggregate `get_device_state()` client. Known fields remain optional, and a failed endpoint must not discard available data. Band `1/28` becomes `(1, 28)` without carrier-aggregation meaning. Signal fields use unit-neutral names with `units_verified=False`. Identifiers/addresses are represented by availability rather than full values; model repr/str omits all details. Carrier evidence remains unknown.

Authentication is an injected session contract, separate from the models/parser and SMS transport. `LiveDeviceService` now composes the production `D2Session` directly; it has no browser-session dependency. The default `D2StatusClient().get_device_state()` returns authentication-required unknown state and performs no I/O; it never copies browser Authorization values. An injected session must honor the shared monotonic deadline (default 20 seconds), cancellation, 256 KiB response limit, TLS verification, redirect rejection, and connection cleanup. The client cannot preempt arbitrary injected code that ignores that contract.

The backend and services remain independent of GUI/browser packages; importing the backend does not connect to a router or carrier. The optional desktop shell uses PySide6, and DITO-specific browser/endpoint rules live behind the carrier adapter. Authentication state crosses the service boundary through closed neutral models. No account-data retrieval, storage or carrier mapping is included. Manual development probes remain separate from runtime and never run at application startup.

```text
src/sim_manager/
├── __init__.py
├── __main__.py                      # native app entry point
├── app.py
├── models.py
├── message_models.py                 # private, carrier-neutral inbox values
├── account_models.py                 # neutral authentication state/events
├── carriers/dito/                    # isolated browser, auth policy and likely OTP
├── services/                        # providers and safe presentation
├── resources/                        # sanitized demo + public D2 certificate
├── ui/                              # Qt window and three pages
└── devices/
    ├── __init__.py
    └── d2/
        ├── __init__.py
        ├── demo.py                   # sanitized fixture → normalized state
        ├── router.py
        ├── messages.py              # SMS envelope → normalized inbox
        ├── errors.py                 # closed safe infrastructure errors
        ├── session.py                # direct login and bounded verified HTTPS
        ├── status.py                 # fixed seven-getter status client
        └── status_parser.py          # Task 005 normalization
tests/
├── test_d2_discovery.py
├── test_d2_discovery_sources.py
├── test_d2_source_evidence.py
├── test_d2_router.py
├── test_d2_router_reliability.py
├── test_d2_status_parser.py
├── test_d2_status_client.py
├── test_device_services.py
├── test_d2_messages.py
├── test_message_services.py
├── test_account_services.py
├── test_dito_otp.py
├── test_dito_auth_policy.py
├── test_dito_auth_observer.js        # synthetic auth observer/response tests
├── test_d2_browser_probe.js          # separate Node development-probe tests
├── gui/test_desktop.py              # separate Qt tests
├── gui/test_messages.py             # synthetic inbox/UI lifecycle tests
├── fixtures/d2/                     # sanitized observations/synthetic source
└── fixtures/dito/                   # public authentication source ledger
tools/
├── d2_discovery.py
├── d2_source_evidence.py
└── d2_browser_probe.js
```

## Offline verification

From this repository root in PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path ./src).Path
python -S -B -m unittest discover -s tests -v
```

The backend/service suite uses only the Python standard library, synthetic socket transcripts/providers, and controlled clocks. Tests block live I/O and require no router, browser, Qt installation, or personal data. GUI tests live separately under `tests/gui/` and are not discovered by this command. Characterization tests retain selected legacy behavior, and regression tests cover the deliberate Task 002 changes. Passing offline tests does not establish compatibility with any router firmware.

With the desktop extra installed, run the separate GUI suite offscreen:

```powershell
$env:PYTHONPATH = (Resolve-Path ./src).Path
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/gui -v
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
```

The final command clears the test-only platform override so a later native launch opens a visible window. GUI tests use fake/offline providers and must not contact the live router or carrier.

The separate router development probe and production DITO authentication observer have offline tests using Node's built-in test runner:

```powershell
node --test tests/test_d2_browser_probe.js tests/test_dito_auth_observer.js
```

No npm packages are required. The Python standard-library suite remains independent of Node and browser packages; it does not execute these JavaScript tests.

Task 004 verification passed 190 Python tests and 36 Node tests, including the supplied sanitized authenticated-report fixture. The development source summaries were intentionally tightened to omit arbitrary dotted string values; production transport behavior and all 78 original transport tests remain unchanged.

Task 005 verification passed **260 Python tests** (190 prior tests plus 31 parser/model and 39 client cases) and **36 Node tests**. All 78 prior SMS transport tests, production SMS transport, development tools/tests/fixtures, and 40 legacy files remain unchanged. No live-router/browser access occurred in Task 005. Syntax, privacy, and tracked/untracked diff/whitespace checks passed.

Task 006 passed **285 backend/service tests**, **30 GUI tests**, and **36 Node tests** on Python 3.13.15 and PySide6/Qt 6.11.2. Native Windows production/demo rendering, refresh, and closure passed with no refresh workers remaining. Editable installation and both installed launch commands worked from outside the repository without `PYTHONPATH`; the wheel includes the exact sanitized demo resource. Legacy/backend integrity, syntax, privacy, and diff/whitespace checks passed. These GUI checks establish no new live-router/authentication capability.

Task 006.1 passed **285 backend/service tests**, **38 GUI tests**, and **36 Node tests**. Native Windows normal/demo layouts were checked on all three pages at 1120×760, 840×600, and maximized (1600×837 on the verification display), without clipping, overlap, or scrolling for these states. Scroll areas remain available for longer content or larger fonts. Backend/model/service files and all 40 legacy files were unchanged; Task 007 was unstarted at that verification point.

Task 007 passed **368 backend/service tests**, **56 GUI tests**, and **36 Node tests** (460 total). Direct local login and two complete seven-getter cycles passed through the native application, including Refresh and LIVE presentation. Verified displayed values were SIM Ready, PIN check Off, LTE/Connected, bands 1/28, RSRP -87, secondary RSRP -95, RSRQ -9, RSSI -76, SINR 23, WAN Connected and address availability Reported; Carrier remained Unknown and signal units remained unverified. The validation window closed cleanly. Both exact installed normal/demo CLI launches exited successfully with empty output and no owned orphan processes. Editable installation, wheel resource checks, syntax, privacy, legacy hashes and tracked/untracked whitespace/diff review passed. The wheel includes the public certificate and exact sanitized demo fixture. Server token lifetime, actual forced-expiry timing, hardware rejected-password code, logout invalidation and other firmware remain unverified; expiry/relogin/error paths are covered offline. No settings changed, credentials persisted or raw authenticated captures were retained. Task 008 was unstarted at that verification point.

Task 009 passed **500 backend/service tests**, **128 GUI tests** and **57 Node tests** (685 total). Synthetic tests cover authentication success/rejection, expiry/reconnect, explicit disconnect, cancellation, stale callbacks, OTP matching/ambiguity/privacy, selected-message matching, the production 20-record request, token/cookie redaction, request restrictions and clean shutdown. Controlled official sign-in reached Connected with validated login, then the local Disconnect button returned Not connected and disposed the profile; responsiveness and exit 0 passed, with zero application log records/private stderr bytes. No account data or private capture was exported. Native blank-profile cleanup, installed normal/demo launches, editable/wheel packaging, syntax, privacy, whitespace/diff and all 40 legacy hashes passed. Actual server expiry/logout/revocation remain untested. Task 010 has not begun; the [foundation plan](plans/active/000-foundation-reboot.md) records the full file inventory and validation.

## Transport assumptions

Task 008 passed **429 backend/service tests**, **84 GUI tests**, and **36 Node tests** (549 total). Controlled native Windows validation against the local D2 performed exactly two inbox getter calls: initial Messages load and its Refresh each returned **3 messages**, available and complete with no issues. List/detail selection matched the normalized content in memory, the GUI remained responsive, both returned record sets were unchanged, and closure cleared message widgets with exit 0. Application stdout/stderr and log-record counts were zero; no SMS values, raw captures or live screenshots were exported. The HTTP session was unnecessary for these inbox reads. Normal/demo installed native launches, editable/wheel packaging, all 50 Python AST parses, TOML/JavaScript syntax, legacy integrity, privacy and tracked/untracked whitespace/diff review passed. No SMS or configuration write was requested; Task 009 was unstarted at that verification point. Full evidence and limits are in `docs/devices/D2-HARDWARE-CAPABILITIES.md`.

The supported path requires an already available direct Telnet shell and the existing `cped` UBus SMS command. Login prompts are rejected; the transport does not enable a shell, authenticate, or discover router/modem capabilities. Task 003 confirmed the default direct shell and standalone-line framing for read-only discovery queries. It did not read SMS, validate the historical SMS marker or payload forms on hardware, or test other firmware versions.

Balanced malformed JSON or shell noise can be skipped. An unclosed leading brace is treated as an incomplete outer object; the parser rejects that response rather than searching inside it for a nested success. Router output must therefore avoid unclosed brace-like shell noise before its response. Telnet option-refusal replies remain best effort: their socket errors are swallowed as in the legacy transport, while cancellation/deadline checks still bound processing.

Cancellation and deadlines use short socket polls (up to 0.5 seconds normally, 0.1 seconds with `stop_event`). Short cancellation polls preserve the legacy 0.5-second idle wait for banner/wake-up reads, capped by their respective 0.7/0.25-second phase deadlines. Connection setup uses a daemon worker and caller polls of at most 0.05 seconds. The caller can abandon a blocked connection attempt, and a late socket is closed. The OS DNS call itself cannot be interrupted; repeated abandoned DNS calls can temporarily accumulate daemon workers. No blocking worker join is required for shutdown.

Diagnostic logs and exception output must mask or omit full phone numbers/MSISDNs, IMSIs, ICCIDs, OTPs, authentication cookies, tokens, and passwords. All SMS bodies and raw SMS responses must be omitted from logs and exception text. Test fixtures use only synthetic messages; live validation reports counts/status without message contents.

## Manual read-only discovery

From the repository root with `PYTHONPATH=src`, list the fixed reviewed queries without hardware access:

```powershell
python -S -B tools/d2_discovery.py --list-queries
```

An explicit `--query` invocation contacts the router. The development tool permits only reviewed read-only queries, uses bounded timeouts/output, and supports Ctrl+C. Normal output omits unknown values and sensitive identifiers. It does not change router settings, invoke guessed vendor/AT commands, or build production detection logic.

Task 004 inspected firmware/web assets first, then verified only getters evidenced by the router's own admin interface. Future status-page discovery may use an existing legitimate router session; passwords, cookies, and tokens must not be logged or stored in the repository. Configuration controls and requests with uncertain side effects remain out of scope. Any observed PLMN/operator values remain neutral evidence; carrier mapping stays deferred. Task 007 subsequently established direct local authentication as described above.

For a legitimate signed-in Brave router tab, print the fixed browser probe offline:

```powershell
python -S -B tools/d2_discovery.py --browser-script
```

Manual execution in that tab's DevTools Console sends only seven firmware-evidenced same-origin GETs. The firmware uses `localStorage.Authorization` and an Authorization header with its credentials interceptor; the probe reuses that session inside the tab and never exports cookies/tokens. No browser-storage or router-setting writes are requested. It accepts only the local HTTPS router origins listed in the script, rejects redirects, enforces a 20-second total deadline and 256 KiB per-response limit, and can be stopped with `SIM_MANAGER_D2_PROBE.cancel()`.

Only a sanitized summary should be shared. Identifier/address/APN/cell values are masked; arbitrary operator/model/version text and unknown values are omitted. Narrow status enums, bands, signal values, and neutral PLMN digit strings may be retained without carrier interpretation. The user manually ran the probe inside the signed-in Brave tab because this environment had no browser connector or exposed remote-debugging port/pipe. All seven GETs returned HTTP/body code 200 with object data, without exporting authorization material.

The report verifies raw `Ready`/`READY`, `Connected`, and `LTE` labels, band string `1/28`, signal strings, and masked identifier field types. Masks hide even empty strings, so identifier contents/validity and cellular address assignment are unknown. Radio units, registration/roaming, actual operator/PLMN, APN/PDP, modem firmware revision, absent/PIN-locked SIM states, and other firmware variants remain unverified. `wirelessinfo` exported no allowlisted fields; that does not prove empty raw data. Task 005 normalizes this evidence without adding carrier mapping or claiming broader hardware validation.

Raw responses are transient unless `--capture-raw` is explicitly requested. That flag saves sensitive data only under the ignored `artifacts/d2-private/` directory; never commit or paste those captures into documentation. It was not used for hardware in Tasks 003/004. See the [D2 hardware capability report](docs/devices/D2-HARDWARE-CAPABILITIES.md) for historical shell queries, firmware provenance, the authenticated GET ledger, and field statuses. Only GET/read operations were requested; firmware-internal side effects were not audited.

The `pyproject.toml` declares a setuptools build backend for future packaging. Building/installing the distribution requires that build tool; source imports and the offline test command above do not.

See [WORKFLOW.md](docs/WORKFLOW.md) for repository boundaries and verification, [AGENTS.md](AGENTS.md) for security/development rules, and the [active foundation plan](plans/active/000-foundation-reboot.md) for findings and deferred tasks.

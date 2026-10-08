# SIM Manager

A lightweight Windows SIM management application in development. Tasks 001–006 and 006.1 are complete within their approved scopes. Task 007 (direct local D2 authentication and live status) is complete. The native PySide6 desktop shell displays normalized device state through Overview, Messages, and Settings. Python 3.11 or newer is required.

Task 007 adds direct router authentication and LIVE status without a browser. Start normal mode, choose **Sign in**, and enter the router username and masked password in SIM Manager. Both fields start blank because the firmware has no verified default username. Credentials are used only in memory and are never saved. Successful sign-in automatically retrieves the seven verified status getters; **Refresh** reads them again. LIVE marks real snapshots; explicit `--demo` remains independent and permanently marked DEMO. Live hardware validation passed: legitimate login, all seven getters, complete normalized state, LIVE GUI display, Refresh and clean shutdown.

The application connects directly to `https://192.168.1.1`, performs no DNS lookup, and rejects redirects. It trusts only the bundled public D2 certificate for that exact default origin, with certificate and IP hostname verification enabled. The observed certificate is valid through 2030-10-26. Other configured private IP origins use ordinary verified TLS unless an explicit certificate is supplied. Certificate replacement requires a reviewed resource update; there is no insecure fallback.

The verified firmware protocol is `POST /web/v1/user/login` with JSON `{username, password}` and no credential transformation. A successful `{code: 200, data: {Authorization: ...}}` creates a private in-memory session; subsequent approved GETs send that opaque value verbatim in the Authorization header. No browser, DevTools, localStorage, cookies or manually copied tokens are required by the implementation. HTTP/body 401 or 403 invalidates the session, stops that refresh cycle and offers Sign in again. No automatic login retry or password retention occurs. Closing cancels work and discards authorization; the source-evidenced logout POST is deliberately unused.

Login has a 20-second deadline; the subsequent seven-getter refresh has one separate 20-second deadline and 256 KiB per-response limit. Both use one cancellable worker, and GUI shutdown joins for at most one second. Safe UI messages distinguish authentication required/rejected, unreachable router, connection/TLS trouble, malformed data and partial status. Carrier stays Unknown; signal units, registration and roaming remain unverified.

## First desktop milestone

The native Qt Widgets shell is a visual milestone. Overview displays safe SIM/network/signal/WAN state with unknown values left explicit and Carrier Unknown. Messages is a page shell; the raw SMS transport is not wired directly into the GUI without a normalized message service. Settings contains read-only router-address/status placeholders and app information, with no credential editing or persistence.

Normal mode initially reports Authentication required without network I/O. Explicit Sign in creates a direct router session and refreshes live status; no browser opens. Explicit `--demo` uses sanitized Task 004 fixture-derived state and labels the UI DEMO. Demo is never substituted silently for live data. The existing snapshot model is named `DeviceState`; no backend rename to the conceptual `DeviceSnapshot` is required.

Refresh uses the service interface outside the GUI thread, blocks overlapping requests, and reports safe loading/error states. Closing requests cooperative cancellation and a worker join bounded to one second; repeated shutdown is non-blocking. Shipped production/demo providers are bounded; arbitrary injected providers that ignore cancellation cannot be forcibly stopped, though daemon workers cannot block process shutdown. Carrier login/account integration, tray behavior, charts, configuration storage and Task 008 remain deferred.

Task 006.1 polishes the existing UI: compact routine status, warnings/errors as banners, prominent Carrier Unknown/Network/SIM information, all six signal fields, compact connection details, and small monochrome navigation icons. Refresh appears only on Overview; Cancel remains available on any page while work is running. The DEMO badge and offline-fixture disclosure persist across every page. Settings groups read-only router and application information; Messages remains unconnected.

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

The `desktop` extra installs `PySide6-Essentials>=6.8,<7`, which supplies the native Qt Widgets shell. Base/backend imports have no runtime dependency on Qt. Production launch offers Sign in for direct router authentication; `--demo` displays sanitized fixture-derived values with a DEMO indicator. Neither mode opens a browser or modifies router settings. Use a normal Windows desktop session for launch; the offscreen setting below is only for GUI tests.

## Current scope

The D2 SMS transport is `sim_manager.devices.d2.router`, originally copied from the read-only legacy reference at `../old/D2-desktop/router.py`. It uses the existing Telnet/UBus inbox path. The default `192.168.1.1:2323` endpoint, three-record read, exact UBus command, and fixed historical marker remain unchanged.

The transport now preserves Telnet state across reads, recognizes a terminated standalone completion-marker line with command echo enabled or disabled, bounds raw received bytes, uses monotonic deadlines, supports cooperative cancellation, and emits generic errors without raw exception chains. Marker text inside command echoes or JSON strings cannot complete a read. Response processing stops at the marker line; trailing JSON or Telnet bytes in the same receive are ignored.

`fetch_sms_response` keeps its five existing positional parameters and adds keyword-only `stop_event` and `max_response_bytes`. An optional event with `is_set()` requests cancellation, reported as `RouterCancelledError`. The default byte limit is 1 MiB per read phase (banner, wake-up, command response), including Telnet control bytes. EOF or a reset raises `RouterDisconnectedError`, a subclass of `RouterConnectionError`.

SMS envelopes remain raw. Stringified or otherwise loosely shaped `data` is preserved, and the last successful outer envelope can still win over a later error envelope. Response selection prevents nested SMS objects from overriding valid or malformed outer envelopes. Transparent-wrapper fallback remains when no top-level envelope exists; traversal stops at any dictionary containing both `code` and `msg`, including error envelopes. The public JSON extraction helper still enumerates nested objects. Message normalization and stronger payload-schema validation are deferred.

Task 005 adds the normalized Device boundary: immutable SIM, network, radio, WAN, carrier-evidence, snapshot, and partial-error models; a D2 parser; and one aggregate `get_device_state()` client. Known fields remain optional, and a failed endpoint must not discard available data. Band `1/28` becomes `(1, 28)` without carrier-aggregation meaning. Signal fields use unit-neutral names with `units_verified=False`. Identifiers/addresses are represented by availability rather than full values; model repr/str omits all details. Carrier evidence remains unknown.

Authentication is an injected session contract, separate from the models/parser and SMS transport. `LiveDeviceService` now composes the production `D2Session` directly; it has no browser-session dependency. The default `D2StatusClient().get_device_state()` returns authentication-required unknown state and performs no I/O; it never copies browser Authorization values. An injected session must honor the shared monotonic deadline (default 20 seconds), cancellation, 256 KiB response limit, TLS verification, redirect rejection, and connection cleanup. The client cannot preempt arbitrary injected code that ignores that contract.

The backend and services remain independent of GUI/browser packages; importing the backend does not connect to a router. The optional desktop shell uses PySide6. No storage/account integration or carrier mapping is included. Manual development probes remain separate from runtime and never run at application startup.

```text
src/sim_manager/
├── __init__.py
├── __main__.py                      # native app entry point
├── app.py
├── models.py
├── services/                        # providers and safe presentation
├── resources/                        # sanitized demo + public D2 certificate
├── ui/                              # Qt window and three pages
└── devices/
    ├── __init__.py
    └── d2/
        ├── __init__.py
        ├── demo.py                   # sanitized fixture → normalized state
        ├── router.py
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
├── test_d2_browser_probe.js          # separate Node development-probe tests
├── gui/test_desktop.py              # separate Qt tests
└── fixtures/d2/                     # sanitized observations/synthetic source
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

The final command clears the test-only platform override so a later native launch opens a visible window. GUI tests use fake/offline providers and must not contact the router or browser.

The separate browser development probe has offline tests using Node's built-in test runner:

```powershell
node --test tests/test_d2_browser_probe.js
```

No npm packages are required. The Python standard-library suite remains independent of Node and browser packages; it does not execute these JavaScript tests.

Task 004 verification passed 190 Python tests and 36 Node tests, including the supplied sanitized authenticated-report fixture. The development source summaries were intentionally tightened to omit arbitrary dotted string values; production transport behavior and all 78 original transport tests remain unchanged.

Task 005 verification passed **260 Python tests** (190 prior tests plus 31 parser/model and 39 client cases) and **36 Node tests**. All 78 prior SMS transport tests, production SMS transport, development tools/tests/fixtures, and 40 legacy files remain unchanged. No live-router/browser access occurred in Task 005. Syntax, privacy, and tracked/untracked diff/whitespace checks passed.

Task 006 passed **285 backend/service tests**, **30 GUI tests**, and **36 Node tests** on Python 3.13.15 and PySide6/Qt 6.11.2. Native Windows production/demo rendering, refresh, and closure passed with no refresh workers remaining. Editable installation and both installed launch commands worked from outside the repository without `PYTHONPATH`; the wheel includes the exact sanitized demo resource. Legacy/backend integrity, syntax, privacy, and diff/whitespace checks passed. These GUI checks establish no new live-router/authentication capability.

Task 006.1 passed **285 backend/service tests**, **38 GUI tests**, and **36 Node tests**. Native Windows normal/demo layouts were checked on all three pages at 1120×760, 840×600, and maximized (1600×837 on the verification display), without clipping, overlap, or scrolling for these states. Scroll areas remain available for longer content or larger fonts. Backend/model/service files and all 40 legacy files are unchanged; Task 007 remains unstarted.

Task 007 passed **368 backend/service tests**, **56 GUI tests**, and **36 Node tests** (460 total). Direct local login and two complete seven-getter cycles passed through the native application, including Refresh and LIVE presentation. Verified displayed values were SIM Ready, PIN check Off, LTE/Connected, bands 1/28, RSRP -87, secondary RSRP -95, RSRQ -9, RSSI -76, SINR 23, WAN Connected and address availability Reported; Carrier remained Unknown and signal units remained unverified. The validation window closed cleanly. Both exact installed normal/demo CLI launches exited successfully with empty output and no owned orphan processes. Editable installation, wheel resource checks, syntax, privacy, legacy hashes and tracked/untracked whitespace/diff review passed. The wheel includes the public certificate and exact sanitized demo fixture. Server token lifetime, actual forced-expiry timing, hardware rejected-password code, logout invalidation and other firmware remain unverified; expiry/relogin/error paths are covered offline. No settings changed, credentials persisted or raw authenticated captures were retained. Task 008 has not begun.

## Transport assumptions

The supported path requires an already available direct Telnet shell and the existing `cped` UBus SMS command. Login prompts are rejected; the transport does not enable a shell, authenticate, or discover router/modem capabilities. Task 003 confirmed the default direct shell and standalone-line framing for read-only discovery queries. It did not read SMS, validate the historical SMS marker or payload forms on hardware, or test other firmware versions.

Balanced malformed JSON or shell noise can be skipped. An unclosed leading brace is treated as an incomplete outer object; the parser rejects that response rather than searching inside it for a nested success. Router output must therefore avoid unclosed brace-like shell noise before its response. Telnet option-refusal replies remain best effort: their socket errors are swallowed as in the legacy transport, while cancellation/deadline checks still bound processing.

Cancellation and deadlines use short socket polls (up to 0.5 seconds normally, 0.1 seconds with `stop_event`). Short cancellation polls preserve the legacy 0.5-second idle wait for banner/wake-up reads, capped by their respective 0.7/0.25-second phase deadlines. Connection setup uses a daemon worker and caller polls of at most 0.05 seconds. The caller can abandon a blocked connection attempt, and a late socket is closed. The OS DNS call itself cannot be interrupted; repeated abandoned DNS calls can temporarily accumulate daemon workers. No blocking worker join is required for shutdown.

Diagnostic logs and exception output must mask or omit full phone numbers/MSISDNs, IMSIs, ICCIDs, OTPs, sensitive SMS bodies, authentication cookies, tokens, and passwords. Returned SMS data is sensitive and must not be logged wholesale.

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

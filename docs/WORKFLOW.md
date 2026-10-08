# Development workflow

The repository root is `C:\PROJECTs\SIM-manager_workspace\sim-manager`. Run project commands there. Initialize Git only in this directory; never initialize Git at the workspace root or include `../old/D2-desktop/` in this repository.

The legacy tree is read-only reference material. Copy approved reusable code into `src/sim_manager/`; never import from the legacy tree at runtime. Compare before/after file lists and SHA-256 hashes when verifying that legacy files remain unchanged.

Read `AGENTS.md`, the relevant docs, and the active plan before changing code. Implement only the approved task. Tasks 001–006 and 006.1 completed the transport foundation, scoped read-only hardware/firmware discovery, carrier-neutral device-state models/normalization, and the native PySide6 shell over services with explicit demo mode. Task 007 direct D2 authentication/live status is complete within its approved scope. Message normalization, carrier mapping/account features, persistent credential storage and Task 008 remain deferred.

## Task 007 direct router authentication

Inspect the active public Vue login/request/interceptor source before implementing any login endpoint, request body, credential transform, token extraction or logout. Record VERIFIED / INFERRED / UNKNOWN separately. `tools/d2_auth_evidence.py` is a development-only fixed-origin public-static-source probe; it never logs in, executes JavaScript, reads browser state or exports raw source. Static request candidates alone do not verify a working protocol. The browser probe remains development-only and is never imported by the application.

The only permitted state-changing requests in Task 007 are legitimate login/session creation and optional verified logout. All status reads remain the seven reviewed GETs. No configuration/SMS/APN/network/band/PIN/Wi-Fi/password/firmware operations, credential guessing or automatic repeated authentication attempts are allowed. Runtime username/password must be entered only into the application dialog (password masked), never Codex chat, command-line arguments, environment variables, config, fixtures or logs. The password is transient; authorization remains private to D2 infrastructure and is discarded on invalidation/close. Python/Qt immutable strings cannot promise physical memory erasure.

Transport checks must cover connect/TLS/send/read cancellation and deadlines, response/header limits, redirect rejection, context-safe errors and session expiration. TLS verification remains enabled by default. The bundled public D2 certificate uses an isolated trust store only for the exact default IP origin; its verified IP SAN permits hostname verification to remain enabled. Explicit anchors for other configured private IP origins also retain hostname verification. Never globally disable certificate checking or suppress unrelated HTTPS failures. The public firmware certificate and IP SAN were recovered directly from the local D2; production never resolves smartbrosettings.net through DNS or follows redirects.

Run backend/service and GUI suites offline with synthetic credentials and response shapes first. Then connect to the D2, launch the normal native application and have the user enter the password there. Verify seven successful GETs, normalized safe fields, LIVE presentation, Refresh and closure; record partial/unavailable results honestly. Do not export raw authenticated captures, tokens, cookies or private identifiers. Session expiry may be simulated offline rather than forcing an unevidenced hardware logout. Recheck independent DEMO mode, packaging, syntax, tracked/untracked whitespace, Git diff and legacy hashes. Do not mark Task 007 complete until protocol implementation and live validation are resolved.

Task 007 final validation on 2026-10-08 (Asia/Irkutsk): **368 backend/service**, **56 GUI** and **36 JavaScript** tests passed with zero failures. The live user-entered login succeeded, followed by all seven getters and a second complete cycle through Refresh; native LIVE values and closure were verified. Wrong-password/expired-session/partial/cancellation/redaction paths use offline fakes rather than deliberate bad hardware logins or forced logout. Exact installed normal/demo CLI commands from the workspace parent, without `PYTHONPATH` or offscreen override, opened native windows and exited 0 with empty output/no owned orphans. Editable installation and wheel build passed; wheel certificate/demo bytes match source and the wheel excludes tools/tests/legacy. All 42 Python files and TOML passed syntax checks; legacy hashes, privacy and tracked/untracked whitespace/diff review passed. The environment reuses the existing PySide6/Qt 6.11.2 installation; a separate fresh isolated Qt dependency install was not required or exercised. Source evidence and firmware trust remain specific to the observed D2 build; server TTL, hardware rejection code and logout behavior remain unknown. Task 008 remains unstarted.

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

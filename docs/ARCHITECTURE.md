# SIM Manager architecture

Intended application layers:

```text
UI
 │
Services
 │
Carrier abstraction
 ├── DITO
 └── Smart
 │
Device abstraction
 └── D2
     └── Quectel modem
```

Task 001 established the Python package and D2 device namespace; Task 002 hardened the existing SMS transport. Task 005 added the normalized device-state boundary:

```text
src/sim_manager/
├── __init__.py
├── __main__.py                       # native module entry point
├── app.py                            # desktop composition
├── models.py                         # carrier-neutral immutable state
├── services/                         # provider and safe presentation
├── ui/                               # Qt window, refresh, three pages
├── resources/d2-demo-report.json      # sanitized offline demo resource
└── devices/
    ├── __init__.py
    └── d2/
        ├── __init__.py
        ├── demo.py                   # fixture reconstruction/normalization
        ├── router.py                 # preserved SMS transport
        ├── errors.py                 # closed privacy-safe infrastructure errors
        ├── session.py                # private direct HTTPS/session infrastructure
        ├── status.py                 # fixed-endpoint aggregate client
        └── status_parser.py          # raw D2 shapes → normalized state
```

`devices/d2/router.py` started as a byte-for-byte copy of the legacy Telnet/UBus SMS transport. Task 002 retains the exact UBus command, default endpoint/read count, and historical marker while adding stateful Telnet decoding, standalone-line completion, bounded reads, monotonic deadlines, cooperative cancellation, and sanitized transport errors. It uses the Python standard library and does not depend on browser, UI, or carrier packages. The new package never imports code from `old/`.

The SMS transport still returns the raw selected SMS envelope; message normalization and payload-schema decisions are deferred. It does not establish direct Quectel communication or carrier support. The new status path is separate from this transport. Task 006 adds services and the first native UI; carrier adapters, normalized message services, storage, and account integration remain future work described in `plans/active/000-foundation-reboot.md`.

Response processing stops at the completed marker line even if trailing JSON or Telnet bytes share the same receive. Envelope selection does not descend into valid or malformed response payloads. Transparent structural wrappers are supported, with traversal stopping at any `code`/`msg` envelope. An unclosed leading brace is rejected rather than used for unsafe nested resynchronization. The public extraction helper's nested enumeration, loosely shaped `data`, last-success selection, and best-effort Telnet refusal errors remain compatibility behavior.

Connection setup runs in a daemon worker so the caller can honor cancellation and its monotonic deadline even while an OS resolver/connect call is blocked. An abandoned worker closes a socket if it eventually arrives. The underlying DNS call cannot be interrupted; repeated abandoned DNS calls may temporarily accumulate daemon workers. No hardware or live-network validation is included in Task 002.

Socket polling remains at most 0.5 seconds normally or 0.1 seconds with cancellation enabled. Banner/wake-up reads retain the legacy 0.5-second idle wait within their respective 0.7/0.25-second phase deadlines; short cancellation polls do not shorten that idle window. Task 002 is verified offline.

Task 003 completed discovery with `tools/d2_discovery.py`, offline probe/parser tests, and hardware evidence. The manually invoked tool reuses transport helpers with a fixed read-only query allowlist, bounded deadlines/output, cooperative cancellation, and privacy-filtered summaries. It is not imported at startup and does not extend the production device API. Raw capture is explicit and limited to an ignored private directory. Findings and uncertainties are recorded in `docs/devices/D2-HARDWARE-CAPABILITIES.md`: Task 003 verified the USB module identity and kernel default-route binding, while SIM/operator/registration/radio runtime fields remained untested. Production transport code and its existing tests were unchanged in Task 003; no carrier interpretation or production models were added.

Task 004 completed read-only cellular telemetry discovery through the active `/opt/web` firmware/admin UI. Development tools include a strict source-evidence helper and a seven-GET same-origin browser probe with sanitized offline fixtures. The user supplied authenticated observations from the legitimate Brave session; authorization remained inside the router origin. Raw Ready/Connected/LTE labels, band/signal strings, and identifier field types were verified, while identifier validity, units, registration, roaming, carrier identity, and modem firmware revision remained unverified. No production device API, carrier detection, or product UI was added in Task 004. Getter execution continues to require firmware/UI evidence of read semantics. The capability report separates source bindings, authenticated values, normalized representations, and interpretation limits.

Task 005 concerns Device → normalized models only. `models.py` defines immutable `SimState`, `NetworkState`, `RadioState`, `WanState`, `CarrierEvidence`, `DeviceIssue`, and `DeviceState` with closed safe enums, optional values, UTC/source metadata, and partial-error information. Repr/str is opaque even if callers supply wrongly typed constructor values. The D2 parser discards full identifiers/addresses and reports availability only; optional operator/APN values remain unset without verified content. Bands preserve reported order, numeric signals have no asserted units, and unknown presence/registration/roaming/PDP/PLMN values stay unknown. Neutral carrier evidence is not a carrier-detection decision.

`D2StatusClient.get_device_state(timeout=20.0, stop_event=None)` aggregates only the fixed seven verified GETs behind the injected `AuthenticatedStatusSession.read_json()` protocol. `StatusResponse(http_status, payload)` stays inside this device boundary and has opaque repr/str. Authentication belongs to the session implementation, not models/parser or the UI. No production browser-session bridge exists yet; the default missing-session path returns an authentication-required snapshot without I/O. No credential/header/token parameters or storage are introduced. An injected implementation owns TLS verification, redirect rejection, body limits, and connection cleanup, and must honor the shared monotonic deadline, cancellation event, and 256 KiB per-response contract; the client cannot forcibly interrupt arbitrary non-cooperative injected code. Authentication failures stop further requests; cancellation/deadline expiry discards late responses while retaining earlier successes. Other endpoint failures remain isolated. Diagnostics contain fixed source keys and closed issue codes rather than raw response/exception text. Development probes are not runtime dependencies. Task 005 completed this boundary with 260 passing Python tests and 36 passing Node tests, retaining the authentication implementation limit.

Task 006 implemented the first native Windows shell with PySide6 Qt Widgets. Historical pywebview/WebView2 discussion describes the legacy app and a possible future carrier-account browser surface; it does not mandate a shell framework. The existing `DeviceState` is the snapshot contract. `services/device.py` defines the credential-free `SnapshotProvider.get_device_state(stop_event=None)` boundary and explicit `LiveDeviceService`/`DemoDeviceService` providers. `services/presentation.py` converts state through `present_device()` into an opaque immutable `DeviceView` containing fixed labels and bounded safe numeric text. Overview/Messages/Settings render only that presentation. UI modules do not import endpoint paths, parse router payloads, read browser storage, or access authentication material. Carrier adapters remain future work; neutral status presentation follows Device → Services → UI.

At the historical Task 006 milestone, production wrapped the Task 005 client without a session and returned authentication-required unknown state with no I/O. Task 007 now composes a direct session as described below. Explicit `--demo` selects a separate offline provider from `resources/d2-demo-report.json`, a packaged byte-for-byte copy of the sanitized Task 004 report. `devices/d2/demo.py` reads it through `importlib.resources`, reconstructs only sanitized envelope fields, and normalizes state with source `demo:d2`; unknown masked identifiers stay unknown. A persistent DEMO indicator distinguishes it from live state, and there is no silent fixture fallback. Carrier always displays Unknown. Router status describes retrieval availability, separately from the network's Connected label. Messages remains a shell until a normalized SMS service exists. Settings is read-only and adds no credential/configuration storage. The optional `desktop` extra uses `PySide6-Essentials>=6.8,<7`; backend/services have no Qt runtime dependency. Development probes and legacy code are not runtime dependencies.

Refresh uses one Python daemon worker, a stop Event, and a result Queue polled every 50 ms by a Qt main-thread timer. Only the main thread changes widgets. Duplicate refreshes are blocked. Closing requests cancellation, stops polling, discards late results, and joins for at most one second; repeat shutdown is non-blocking and no QThread ownership/lifetime is introduced. Shipped providers are bounded/cooperative. Arbitrary injected providers that ignore cancellation cannot be forcibly killed and may outlive the window as daemon threads; they cannot block process shutdown. The window starts at 1120×760 with a minimum of 840×600. Task 006 passed 285 backend/service, 30 GUI, and 36 Node tests plus native Windows production/demo launch/refresh/close and editable/wheel packaging checks. The foundation plan remains active for deferred work.

Task 007 is complete within its direct-router scope. `D2Session` owns in-memory authorization, HTTPS connection cleanup and session invalidation. `LiveDeviceService.authenticate(password, username=..., stop_event=...)` performs one explicit sign-in attempt and then obtains a normalized snapshot; the UI never sees authorization or raw responses. Authentication and refresh share the existing single worker. A runtime dialog starts with blank username/password fields and clears both fields and edit history on submit/dismissal; the password is masked. Closed service errors distinguish rejection, malformed authentication, timeout, unreachability, connection/TLS failure and cancellation. Successful real snapshots show LIVE, including usable partial snapshots; expired sessions show Authentication required and allow explicit sign-in again. Demo never authenticates or contacts the router.

The new transport restricts origins to configured HTTPS private IP literals and status paths to the seven reviewed getters. Nonblocking connect, TLS handshake, send and receive use a shared monotonic deadline and short cancellation polls, without DNS workers. Redirects and oversized/malformed responses are rejected, and connections always close. For the exact default `https://192.168.1.1` origin, the bundled public firmware certificate is the sole trust anchor, with hostname verification enabled because its SAN includes the IP. Other configured private IP origins use system trust unless an explicit anchor is provided; hostname verification stays enabled. No global TLS setting changes. Shutdown cancels active work and discards authorization without an unevidenced logout request. Active firmware source verifies `POST /web/v1/user/login`, JSON username/password without transformation, and success envelope `code=200` with `data.Authorization`. That opaque value is validated as bounded header-safe ASCII, stored privately and sent verbatim only to the seven getters. No browser state or cookie jar is used. HTTP/body authentication failure invalidates even when cancellation/timeout wins presentation priority. Login is bounded to 20 seconds, followed by a separate 20-second shared refresh deadline. Server token lifetime is unknown; a 15-minute admin-UI inactivity timer is source evidence only. Logout is source-evidenced but deliberately unused. Direct application login and two complete seven-getter cycles, LIVE rendering, Refresh and clean shutdown passed on hardware. No cookie/browser binding was required for this observed firmware/session; no server TTL or runtime logout result is claimed. Task 008 remains unstarted.

# SIM Manager architecture

## Current SIM-first composition

`sim_models.py` defines immutable private SIM profiles: an independent UUID,
custom name, optional full phone number, a neutral carrier choice, an optional
verified identity fingerprint, runtime active flag and associated `AccountState`.
`services/sim_profiles.py` binds those profiles to normalized `DeviceState`.
The D2 parser uses only existing `UICCID` and `MSISDN` fields from the same seven
GETs. It retains a domain-separated SHA-256 fingerprint only for unmasked ASCII
19/20-digit `89`-prefixed ICCIDs with a valid Luhn check digit. This is a
conservative syntax policy, not proof of ownership, issuer or universal firmware
compatibility. Invalid/masked/unsupported values stay unverified. Phone numbers
are display metadata and cannot match a saved profile. IMSIs are not retained.

Known identity observations activate exactly one saved profile; unknown SIMs
offer optional creation. A profile without verified identity remains active only
within a continuous observation context. Saving never invents identity evidence.
Unsuccessful SIM/identity reads preserve the previous known context; a successful
read establishing loss/change clears the old binding. User-supplied carrier
labels support Unknown or DITO only; no carrier mapping/Smart adapter is added.

`storage/sim_profiles.py` stores bounded metadata with current-user Windows
DPAPI protection, atomic encrypted-file replacement and closed errors. There is
no plaintext fallback. Only metadata fields persist, excluding active/account
states, credentials, tokens and messages. The production composition uses the
per-user app-data location; demo and explicit provider injection use memory.
The router credential store and memory-only MyDITO browser remain separate.

The native navigation is Home → SIMs → Messages → History → Settings. Home
retains all normalized D2 details and adds active-profile presentation and a
Messages action. Account-data fields remain explicitly unavailable. SIMs owns
the existing account controls, permitted only for the inserted DITO profile.
Browsing another saved row changes selection alone. Account association records
the profile that initiated login, without claiming its subscriber number was
verified against the inserted SIM. Settings owns router/app
information and the existing Forget router login control; History has no service.

MainWindow observes status through the profile service. A physical context change
disconnects the old carrier session, revokes copied OTP state, cancels inbox work,
clears rows/details/count and advances an inbox generation. Late old results are
discarded; user refresh reads the newly bound context. Closed-state account signals
are also checked against the service's current state before GUI/profile delivery.
Authentication failures cannot imply removal and do not disconnect a SIM account.
Existing transport endpoints, independent SMS authentication and bounded shutdown
remain unchanged. Full numbers are allowed in normal UI, never diagnostics.

## Historical foundation layers

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
├── message_models.py                 # private carrier-neutral inbox values
├── account_models.py                 # neutral account state and auth events
├── carriers/dito/                    # private browser, auth policy, likely OTP
├── services/                         # provider and safe presentation
├── ui/                               # Qt window, refresh, three pages
├── resources/d2-demo-report.json      # sanitized offline demo resource
└── devices/
    ├── __init__.py
    └── d2/
        ├── __init__.py
        ├── demo.py                   # fixture reconstruction/normalization
        ├── router.py                 # preserved SMS transport
        ├── messages.py               # raw SMS envelope → normalized inbox
        ├── errors.py                 # closed privacy-safe infrastructure errors
        ├── session.py                # private direct HTTPS/session infrastructure
        ├── status.py                 # fixed-endpoint aggregate client
        └── status_parser.py          # raw D2 shapes → normalized state
```

`devices/d2/router.py` started as a byte-for-byte copy of the legacy Telnet/UBus SMS transport. Task 002 retains the exact UBus command, default endpoint/read count, and historical marker while adding stateful Telnet decoding, standalone-line completion, bounded reads, monotonic deadlines, cooperative cancellation, and sanitized transport errors. It uses the Python standard library and does not depend on browser, UI, or carrier packages. The new package never imports code from `old/`.

The SMS transport still returns the raw selected SMS envelope. Task 008 adds message normalization and schema validation above that preserved transport, as described below. It does not establish direct Quectel communication or carrier support. The status path is separate from SMS retrieval. Task 006 added services and the first native UI; Task 009 adds the DITO authentication adapter described below. Account data, Smart integration, carrier mapping and storage remain deferred in `plans/active/000-foundation-reboot.md`.

Response processing stops at the completed marker line even if trailing JSON or Telnet bytes share the same receive. Envelope selection does not descend into valid or malformed response payloads. Transparent structural wrappers are supported, with traversal stopping at any `code`/`msg` envelope. An unclosed leading brace is rejected rather than used for unsafe nested resynchronization. The public extraction helper's nested enumeration, loosely shaped `data`, last-success selection, and best-effort Telnet refusal errors remain compatibility behavior.

Connection setup runs in a daemon worker so the caller can honor cancellation and its monotonic deadline even while an OS resolver/connect call is blocked. An abandoned worker closes a socket if it eventually arrives. The underlying DNS call cannot be interrupted; repeated abandoned DNS calls may temporarily accumulate daemon workers. No hardware or live-network validation is included in Task 002.

Socket polling remains at most 0.5 seconds normally or 0.1 seconds with cancellation enabled. Banner/wake-up reads retain the legacy 0.5-second idle wait within their respective 0.7/0.25-second phase deadlines; short cancellation polls do not shorten that idle window. Task 002 is verified offline.

Task 003 completed discovery with `tools/d2_discovery.py`, offline probe/parser tests, and hardware evidence. The manually invoked tool reuses transport helpers with a fixed read-only query allowlist, bounded deadlines/output, cooperative cancellation, and privacy-filtered summaries. It is not imported at startup and does not extend the production device API. Raw capture is explicit and limited to an ignored private directory. Findings and uncertainties are recorded in `docs/devices/D2-HARDWARE-CAPABILITIES.md`: Task 003 verified the USB module identity and kernel default-route binding, while SIM/operator/registration/radio runtime fields remained untested. Production transport code and its existing tests were unchanged in Task 003; no carrier interpretation or production models were added.

Task 004 completed read-only cellular telemetry discovery through the active `/opt/web` firmware/admin UI. Development tools include a strict source-evidence helper and a seven-GET same-origin browser probe with sanitized offline fixtures. The user supplied authenticated observations from the legitimate Brave session; authorization remained inside the router origin. Raw Ready/Connected/LTE labels, band/signal strings, and identifier field types were verified, while identifier validity, units, registration, roaming, carrier identity, and modem firmware revision remained unverified. No production device API, carrier detection, or product UI was added in Task 004. Getter execution continues to require firmware/UI evidence of read semantics. The capability report separates source bindings, authenticated values, normalized representations, and interpretation limits.

Task 005 concerns Device → normalized models only. `models.py` defines immutable `SimState`, `NetworkState`, `RadioState`, `WanState`, `CarrierEvidence`, `DeviceIssue`, and `DeviceState` with closed safe enums, optional values, UTC/source metadata, and partial-error information. Repr/str is opaque even if callers supply wrongly typed constructor values. The D2 parser discards full identifiers/addresses and reports availability only; optional operator/APN values remain unset without verified content. Bands preserve reported order, numeric signals have no asserted units, and unknown presence/registration/roaming/PDP/PLMN values stay unknown. Neutral carrier evidence is not a carrier-detection decision.

`D2StatusClient.get_device_state(timeout=20.0, stop_event=None)` aggregates only the fixed seven verified GETs behind the injected `AuthenticatedStatusSession.read_json()` protocol. `StatusResponse(http_status, payload)` stays inside this device boundary and has opaque repr/str. Authentication belongs to the session implementation, not models/parser or the UI. No production browser-session bridge exists yet; the default missing-session path returns an authentication-required snapshot without I/O. No credential/header/token parameters or storage are introduced. An injected implementation owns TLS verification, redirect rejection, body limits, and connection cleanup, and must honor the shared monotonic deadline, cancellation event, and 256 KiB per-response contract; the client cannot forcibly interrupt arbitrary non-cooperative injected code. Authentication failures stop further requests; cancellation/deadline expiry discards late responses while retaining earlier successes. Other endpoint failures remain isolated. Diagnostics contain fixed source keys and closed issue codes rather than raw response/exception text. Development probes are not runtime dependencies. Task 005 completed this boundary with 260 passing Python tests and 36 passing Node tests, retaining the authentication implementation limit.

Task 006 implemented the first native Windows shell with PySide6 Qt Widgets. Historical pywebview/WebView2 discussion describes the legacy app; it does not mandate a shell framework. The existing `DeviceState` is the snapshot contract. `services/device.py` defines the credential-free `SnapshotProvider.get_device_state(stop_event=None)` boundary and explicit `LiveDeviceService`/`DemoDeviceService` providers. `services/presentation.py` converts state through `present_device()` into an opaque immutable `DeviceView` containing fixed labels and bounded safe numeric text. Overview and Settings consume that presentation; Task 008 gives Messages a separate normalized inbox service. UI modules do not import endpoint paths, construct UBus commands, parse router payloads, read browser storage, or access authentication material. Neutral status and inbox presentation follow Device → Services → UI; Task 009 introduces Carrier → Services → UI for authentication.

At the historical Task 006 milestone, production wrapped the Task 005 client without a session and returned authentication-required unknown state with no I/O. Task 007 now composes a direct session as described below. Explicit `--demo` selects a separate offline provider from `resources/d2-demo-report.json`, a packaged byte-for-byte copy of the sanitized Task 004 report. `devices/d2/demo.py` reads it through `importlib.resources`, reconstructs only sanitized envelope fields, and normalizes state with source `demo:d2`; unknown masked identifiers stay unknown. A persistent DEMO indicator distinguishes it from live state, and there is no silent fixture fallback. Carrier always displays Unknown. Router status describes retrieval availability, separately from the network's Connected label. Messages was a shell at this milestone; its Task 008 service is described below. Settings began as read-only information and Task 009 adds account authentication controls without credential/configuration storage. The optional `desktop` extra uses `PySide6-Essentials>=6.8,<7` and `PySide6-Addons>=6.8,<7`; WebEngine imports occur only on explicit carrier Connect. Backend/services have no Qt runtime dependency. Development probes and legacy code are not runtime dependencies.

Refresh uses one Python daemon worker, a stop Event, and a result Queue polled every 50 ms by a Qt main-thread timer. Only the main thread changes widgets. Duplicate refreshes are blocked. Closing requests cancellation, stops polling, discards late results, and joins for at most one second; repeat shutdown is non-blocking and no QThread ownership/lifetime is introduced. Shipped providers are bounded/cooperative. Arbitrary injected providers that ignore cancellation cannot be forcibly killed and may outlive the window as daemon threads; they cannot block process shutdown. The window starts at its minimum 840×600 size and remains resizable/maximizable. Task 006 passed 285 backend/service, 30 GUI, and 36 Node tests plus native Windows production/demo launch/refresh/close and editable/wheel packaging checks. The foundation plan remains active for deferred work.

Task 007 is complete within its direct-router scope. `D2Session` owns in-memory authorization, HTTPS connection cleanup and session invalidation. `LiveDeviceService.authenticate(password, username=..., stop_event=...)` performs one explicit sign-in attempt and then obtains a normalized snapshot; the UI never sees authorization or raw responses. Authentication and refresh share the existing single worker. A runtime dialog starts with blank username/password fields and clears both fields and edit history on submit/dismissal; the password is masked. Closed service errors distinguish rejection, malformed authentication, timeout, unreachability, connection/TLS failure and cancellation. Successful real snapshots show LIVE, including usable partial snapshots; expired sessions show Authentication required and allow explicit sign-in again. Demo never authenticates or contacts the router.

The new HTTPS transport restricts origins to configured HTTPS private IP literals and status paths to the seven reviewed getters. Nonblocking connect, TLS handshake, send and receive use a shared monotonic deadline and short cancellation polls, without DNS workers. Redirects and oversized/malformed responses are rejected, and connections always close. For the exact default `https://192.168.1.1` origin, the bundled public firmware certificate is the sole trust anchor, with hostname verification enabled because its SAN includes the IP. Other configured private IP origins use system trust unless an explicit anchor is provided; hostname verification stays enabled. No global TLS setting changes. Shutdown cancels active work and discards authorization without an unevidenced logout request. Active firmware source verifies `POST /web/v1/user/login`, JSON username/password without transformation, and success envelope `code=200` with `data.Authorization`. That opaque value is validated as bounded header-safe ASCII, stored privately and sent verbatim only to the seven getters. No browser state or cookie jar is used. HTTP/body authentication failure invalidates even when cancellation/timeout wins presentation priority. Login is bounded to 20 seconds, followed by a separate 20-second shared refresh deadline. Server token lifetime is unknown; a 15-minute admin-UI inactivity timer is source evidence only. Logout is source-evidenced but deliberately unused. Direct application login and two complete seven-getter cycles, LIVE rendering, Refresh and clean shutdown passed on hardware. No cookie/browser binding was required for this observed firmware/session; no server TTL or runtime logout result is claimed. Task 008 was unstarted at that verification point.

Task 008 completes the read-only Messages path, including controlled live SMS validation:

```text
devices/d2/router.fetch_sms_response()
    ↓
devices/d2/messages.D2MessageClient / normalize_messages()
    ↓
message_models.Message / MessageInbox
    ↓
services/messages.LiveMessageService
    ↓
ui/messages_refresh.MessagesRefreshController → ui/pages/messages.MessagesPage
```

The device client calls only the preserved `sms.get.inboxdata` Telnet/UBus command at `192.168.1.1:2323`, with `StartPos=0`. Task 008 used `ReadNum=3`; the raw transport and standalone `D2MessageClient` retain that default. Task 009's production `LiveMessageService` requests `ReadNum=20` through the existing getter parameter, without adding a new command or paging API. HTTP admin authentication and SMS transport remain separate: no HTTP session, Authorization value, router password, or carrier rule reaches the SMS layer. An existing direct shell is required; Telnet login prompts produce a safe SMS authentication-required outcome without credential reuse or a guessed login protocol. No SMS send, delete, mark-read, configuration, or AT command is added.

`normalize_messages()` accepts the legacy-evidenced success envelope and object or JSON-string `data.ItemList`. Immutable `Message` values carry optional identity from `SmsId`, sender from `number`, raw joined date/time text from `smsdate`/`smstime`, and body from `content`; immutable `MessageInbox` carries availability, partial status, and closed issue codes. Missing fields stay unknown or empty. Malformed rows cannot discard readable rows, unknown shapes fail safely, and only an explicit empty ItemList establishes an empty inbox. Exact duplicate-ID rows collapse; conflicting rows with the same ID remain in router order. The service has no cache, persistence, carrier imports, or OTP matcher. Task 009's carrier matcher consumes individual normalized Messages without changing generic retrieval.

Legacy source establishes the field names, not broader firmware semantics. The historical Task 008 three-record window and current production 20-record window have no full-inbox paging or verified newest-first ordering. Timestamp format/timezone, ID uniqueness, `readed` meaning, storage/source metadata, alternate firmware shapes, and modem encoding conversions remain unverified. Date/time are displayed as reported; no timezone, chronological sorting, read/unread status, or storage label is invented. The transport retains UTF-8 replacement decoding and a 1 MiB raw-wire cap per read phase; normalization replaces unsafe controls/lone surrogates and marks affected entries partial. Requests retain the 3-second connect and 30-second response limits, cooperative cancellation, and a 36-second client deadline that discards late results. Arbitrary injected fetchers must honor the same bounded/cancellable contract.

Opening Messages performs its first read. Selection displays the complete body in a read-only plain-text widget; sender/timestamp labels also force plain text, so SMS content is not interpreted as markup or links. Messages owns an independent Refresh/Cancel controller with one daemon worker, Event/Queue handoff, 50 ms main-thread polling, and an overlap guard. Existing content remains visible during retrieval and after cancellation/failure; readable partial results replace the inbox with a warning, while an all-malformed partial result preserves the previous display. Overview refresh and authentication do not schedule or cancel SMS reads. Window shutdown cancels both controllers before sharing a one-second join budget, stops polling, detaches queued results, and clears message widgets/model references. Non-cooperative injected daemon providers retain the documented lifecycle limit.

Real SMS bodies, OTP values, and sender identifiers may appear in the requested inbox UI but never in application logs, diagnostic exception text, fixtures, or captured live-test output. Tests and demo mode use synthetic messages only. Message/MessageInbox repr and str omit all private fields. Raw envelopes are normalized inside the device boundary and discarded; contents remain only in memory, with no file writes or persistence. Errors crossing into the UI contain only closed safe codes/messages. Explicit `--demo` selects `DemoMessageService` with synthetic messages, keeps DEMO visible, and rejects a live message provider; live mode rejects demo providers and never substitutes demo content after failure. Task 009 can consume normalized inbox results for a carrier-specific likely OTP and explicit user copy, without altering shared retrieval or adding automation.

Controlled native Windows validation on 2026-10-08 read the existing getter exactly twice: first navigation and Messages Refresh, each yielding three complete messages with no issues. The actual envelope has JSON-string `data`, an `ItemList` array, integer `SmsId`, string number/date/time/content fields, and boolean `readed`; read-state semantics remain unknown. List/full-detail consistency was checked only in memory. The event loop remained responsive, both returned record sets (including raw read metadata) were identical, widgets cleared on closure, and no logs/output/captures contained SMS values. No HTTP session was required and no write command was sent. All 429 backend/service, 84 GUI and 36 Node tests passed; legacy and existing status/session infrastructure remain unchanged.

## D2 remembered admin login

The separately authorized D2 login UX adds `storage/windows_credentials.py` below `services/router_login.py`; it does not change the carrier adapter or MyDITO lifecycle. The composition root wraps the default production `LiveDeviceService` in `D2LoginService` with an origin-scoped Windows store. DEMO and injected providers get neither real vault access nor implicit login. Startup's idempotent `start_initial_load()` attempts loaded credentials once or uses the existing no-session refresh. An automatic failure opens the normal masked dialog; it never repeats the login.

`WindowsD2CredentialStore` lazily calls native CredReadW/CredWriteW/CredDeleteW/CredFree. An application-owned generic credential uses current-user/current-computer persistence (`CRED_PERSIST_LOCAL_MACHINE`), with both fields in a bounded versioned UTF-16LE blob and no separate username metadata. Targets are hashed canonical private HTTPS router origins. No file/database/plaintext fallback, DITO entry, cookie or Authorization persistence exists. Mutable temporary/read buffers are wiped before release; Python strings cannot promise physical memory erasure. The backend is injectable and offline tests never access the actual vault. Native API behavior follows [Microsoft's credential contract](https://learn.microsoft.com/en-us/windows/win32/api/wincred/ns-wincred-credentialw).

The dialog owns the hidden-by-default eye, opt-in checkbox and transient autofill only. Credentials transfer once to the cancellable worker, without entering DeviceState/result queues/diagnostics. The service saves only after a normalized response and strict current session proof, with no cancellation or revocation. Unchecking Remember deletes an older entry only after successful authentication. Storage errors remain closed issues and fixed notices. An unavailable store does not prevent manual login.

Forget cancels current status work, revokes the service generation, invalidates the reusable D2 session, deletes the credential and clears open-dialog fields. It leaves MyDITO and the independent SMS path untouched. Save/delete share a separate storage lock; native calls do not hold the state lock, so shutdown revokes promptly and retains the existing bounded worker join. A late successful write is removed when its attempt was forgotten, cancelled or closed. The Settings Forget button is disabled while status work is busy. Authorization is always discarded on closure, independently of a deliberately remembered admin credential.

## Task 009 — DITO authentication and session lifecycle

Implementation, offline verification and controlled live account validation are complete. This task adds authentication only. It does not implement balances, promos, allowances, Smart integration, carrier detection, SMS sending or Task 010.

```text
Official MyDITO user sign-in
    ↓
carriers/dito/browser.DitoBrowserSurface + auth_policy / auth_observer.js
    ↓ closed AuthEvent only
services/accounts.DitoAccountService
    ↓ immutable neutral AccountState
ui/accounts.AccountControls in Settings

Existing MessageInbox → services/accounts.offer_otp()
    → carriers/dito.match_otp(Message) → explicit Copy OTP
```

The application composition injects a lazy browser factory into the service; `ui/` imports only normalized account models and the service interface. Creating or importing a service starts no browser/network activity. An explicitly clicked Connect opens `https://my.dito.ph/` in a self-contained, nonmodal Qt WebEngine surface; the user enters credentials, CAPTCHA and OTP and handles the site's consent. No native credential fields, normal browser profile, DevTools snippets, browser extensions or manually copied cookies are required. Public first-party source inspection, exact URLs, content hashes and source-only limitations are recorded in [tests/fixtures/dito/auth-source-evidence.json](../tests/fixtures/dito/auth-source-evidence.json).

The unnamed `QWebEngineProfile` is off record, with memory cache and no persistent cookies. Its state belongs entirely to the carrier surface; no cookie/token extraction crosses into services or UI. Navigation and requests require the exact HTTPS MyDITO origin. `auth_policy.py` allows only evidenced authentication, CAPTCHA, SMS-code request, consent and bootstrap operations plus first-party authentication assets. It blocks subscriber/customer details, balances, allowances, promos, purchases, password reset, router origins and external analytics/debug resources. It also denies the protected `layouts__BaseLayout` and `p__Home` async script families: public source shows that they mount account balance/usage bootstrap and check auxiliary subscriber details. The official login-success effect installs the site's session before pushing `/pto/home`; preventing those lazy account views preserves that authentication milestone without running their later guards or account retrieval. No site history, request body or response is rewritten. The browser hides after the observed success while retaining its memory-only profile; the account website view is deferred. Controlled live sign-in confirmed compatibility for the observed account/site build.

The main-frame observer observes the site's existing fetch flow without making requests, reading submitted fields or exporting headers/storage. It parses only the narrow login/logout result; unrelated and account-data response bodies are ignored. Authentication requires strict boolean `loginSuccess === true` from the official login path/method and subsequent exact `/pto/home` navigation after the site's session/consent effect. The browser checks the trusted route again before publishing `AUTHENTICATED`; URL/DOM hints alone are insufficient. Native-page console messages are discarded, callbacks return only closed enums, and raw browser errors are replaced by safe outcomes. Certificate errors are rejected. Downloads, file access, popups, permissions, site clipboard access and unsafe debugging/TLS environment overrides are denied.

`AccountState` carries only phase, validity, closed issue, likely-OTP availability and demo mode; repr/str is opaque. `DitoAccountService` owns one surface and generation-guards every callback. Repeated Connect while connecting raises the existing sign-in window without another attempt. Rejection leaves the page available for user retry; an authenticated event establishes Connected with validated-at-observation state. Evidence of authentication failure can produce Expired; returning to the root login route conservatively disconnects, including full document navigation that creates a fresh observer. No TTL or continued server validity is inferred. There is no automatic renewal or login loop. Cancellation, disconnect, expiry and shutdown revoke callbacks before closing and clear the private candidate. Browser probe/load timers are bounded, stale callbacks return before accessing deleted Qt pages, and deferred destruction completes the page before its profile.

Disconnect disposes of the application's local session rather than invoking an unverified server logout. The official logout source is documented, but remote token revocation has not been live-verified. Restart requires fresh sign-in; no Windows credential store, config persistence, password retention or exported raw cookies/tokens is introduced. Explicit `DemoAccountService` has only synthetic connected/disconnected states, no browser/network/credentials/OTP, and remains visibly DEMO.

The existing Messages `inbox_ready` signal can offer an inbox to the account service only while connecting. Shared device/message models and retrieval remain carrier-neutral; the production request window expands to 20 records using the existing getter parameter. `carriers/dito/otp.py` applies the historical case-insensitive DITO sender and exact authentication-code phrase with six ASCII digits. This is a likely-code heuristic, without freshness, timezone, ordering, account binding or authenticity claims. One distinct candidate is retained temporarily; conflicting inbox codes suppress the action. Selecting the intended SMS offers that individual normalized Message and narrows the candidate, without carrier parsing in the Messages page. The UI shows availability, never the code, and copies it only on the user's click. It adds no SMS polling, automatic fill or automatic submission. The user pastes and submits within MyDITO; end-of-state/shutdown clears the clipboard only if it still holds the application's copied code.

Task 009 controlled D2 validation returned a safe `MALFORMED_RESPONSE` for a 100-record read and a complete 20-message result for the chosen 20-record window, including a likely OTP beyond the first three returned records. Validation exported only counts/status; bodies, identifiers, senders and code values stayed private in memory. The standalone client/raw transport defaults remain three records, and historical Task 008's two three-record reads above remain unchanged evidence. This retrieval result does not establish chronology, freshness or a DITO account session.

Verification passed 500 backend/service, 128 GUI and 57 Node tests (685 total), including synthetic success/rejection/expiry/reconnect, explicit disconnect, cancellation, late callbacks, conservative full-document disconnect, OTP ambiguity/privacy, selected-message matching, the production 20-record request and token/cookie redaction. The controlled official sign-in established strict login/route proof and Connected/validated GUI state; clicking local Disconnect returned Not connected, disposed the profile and closed cleanly with responsive UI, zero application log records and private stderr bytes. The allowlist blocked two non-auth API attempts and 15 external requests while admitting 12 auth/bootstrap requests. A native blank-profile check confirmed memory-only profile settings, empty stderr and page-before-profile cleanup; packaging/native launch and integrity checks also passed. Actual server expiry/logout/revocation and other site builds remain unverified, without a guessed TTL.

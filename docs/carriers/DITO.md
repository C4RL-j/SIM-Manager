# DITO Adapter

Status: Task 009 authentication/session lifecycle complete with controlled live validation. Account-data retrieval and Task 010 are unstarted.

## Authentication

The [official DITO website](https://dito.ph/) links MyDITO Account to [https://my.dito.ph/](https://my.dito.ph/). The application opens that exact HTTPS origin only after **SIMs → active DITO profile → DITO Account → Connect DITO**. A dedicated unnamed Qt WebEngine profile is off the record, with memory cache, no persistent cookies/permissions and no access to the user's normal browser profile. All fields, OTP/security challenges and consent are handled by the official site. SIM Manager does not read input values, copy browser cookies/tokens/storage, or supply credentials. Base/backend imports stay independent of Qt; the desktop extra includes Qt WebEngine through PySide6-Addons.

The browser/page/request policy and source-backed observer live under `carriers/dito/`. `services/accounts.py` publishes neutral opaque `AccountState`; the GUI hosts compact controls and receives closed state only. The observer wraps only the site's existing first-party fetch flow, never initiates requests, and observes strict top-level `loginSuccess === true` from the official login POST **and** the subsequent exact `/pto/home` transition. The transition follows any required user Privacy Statement/Agree action and site-owned session installation. Neither a URL alone nor token/cookie presence is accepted as authentication proof. The observer returns only closed events; no raw response reaches Python/UI.

The request allowlist permits evidenced official manual auth, sign-in SMS/captcha, configuration/legal bootstrap and first-party static assets. Subscriber/customer details, balances, allowances, promos, purchases, password reset, router origins, external analytics/debug scripts and unknown origins are blocked. Protected BaseLayout/Home script families are also blocked because their subscriber guard and account bootstrap exceed authentication scope; no account view is rendered. Current source tolerates a missing automatic subscriber-detail result before its success transition; controlled live sign-in confirmed that the restricted authentication-only handoff succeeds for the observed account/site build.

## Evidence and legacy audit

The sanitized source/validation ledger is `tests/fixtures/dito/auth-source-evidence.json`: official URLs, public asset hashes/offsets, classified facts, closed live outcomes and unknowns. It contains no authenticated capture or credential value. Source inspection on 2026-10-08 verified the site's same-origin POST `/ecare/webs/user/login`, strict success field, optional consent, success route, source-only GET logout returning numeric JSON zero, and HTTP 401/`PORTAL-SECURITY` login-required handling. Controlled sign-in verified the strict success/route signal and GUI session establishment; actual server logout/expiry remain source-only/offline evidence. No fixed server lifetime was found.

| Classification | Evidence / disposition |
| --- | --- |
| VERIFIED SOURCE | Legacy official MyDITO URL (`desktop.py:32`) remains linked by DITO. Current official public bundles establish manual SMS/password sign-in, consent and success/expiry handling. Official FAQ documents six-digit SMS authentication. |
| INFERRED | Legacy DITO sender/phrase OTP heuristic, first-match-as-latest, naive 150-second freshness and URL-only success detection. Only the cautious likely-OTP heuristic is retained; no freshness/account binding is claimed. |
| OBSOLETE | Legacy no-submit README conflicts with later automatic submission; missing watcher/cache modules and pywebview/account overlays are excluded. |
| UNSAFE TO REUSE | Persistent WebView profile/saved subscriber numbers, unguarded DOM injection, automatic OTP clipboard/fill/submission, raw watcher/SMS-ID diagnostics and additive long worker shutdown. Legacy remains unchanged/read-only. |

## OTP behavior

`carriers.dito.match_otp(Message)` uses the legacy-evidenced sender `DITO` and six ASCII digits followed by authentication-code wording as a **likely** match. The generic message model/service has no carrier imports or OTP regex. A user-refreshed Messages result can offer one distinct candidate while sign-in is in progress; ambiguous different codes offer none. Selecting a specific message explicitly narrows matching to that message. There is no additional SMS polling, timestamp/freshness assumption, account binding, automatic fill or submission. The user can explicitly **Copy OTP**, paste it into MyDITO, and submit there. No code is displayed in diagnostic state or logs. Temporary candidate and app-owned clipboard contents are cleared on connection, cancellation, disconnect or shutdown; unrelated clipboard changes are preserved.

During controlled validation the original three-record window showed older messages. The existing getter returned 20 complete messages with one likely match beyond the first three; a 100-record request failed malformed-response normalization. Production Messages now requests a validated 20-record window; raw transport/standalone-client defaults remain three. Native load and Refresh each displayed 20 complete messages, with consistent selection/detail, responsive UI and cleared content on closure. Only counts/status/schema were exported, with no SMS capture or screenshot. This verifies matching for the observed inbox, without proving current-code freshness, account binding, full-inbox paging or newest-first ordering.

## Session lifecycle and storage

States are Not connected, Sign in with DITO, Connected, Session expired and safe connection errors. `SessionValidity.VALIDATED` records the observed successful login; it does not promise continued server validity or a guessed TTL. A rejected login leaves the official form open for another explicit user attempt. No silent retries occur. Verified auth failures invalidate the session; return to sign-in or a new document after connection conservatively disconnects because its observer context has reset. Reconnect starts a fresh isolated profile. Cancel and application closure revoke generations before browser disposal, so late callbacks cannot restore a session.

**Disconnect** is local disposal of this application's entire isolated profile/page, including its site-owned session storage; it does not claim remote server revocation. The source-evidenced server logout is not automatically called. Session, browser cookies/tokens, user inputs and temporary OTPs are never persisted to config, fixtures, captures or credential storage. Restart requires sign-in again. Browser memory isolation and dropping references do not promise forensic erasure of process memory or OS paging.

Site JavaScript console output is discarded. Exceptions, navigation/loading metadata and service errors never export raw text, URLs with identifiers, cookies/tokens, passwords, OTPs, SIM identifiers or SMS content. Unknown schemes/popups/downloads/file selection/permissions, certificate exceptions and unsafe external debug/browser flags are rejected. An initial page load has a 30-second limit and probes have a 5-second limit; user sign-in has no invented inactivity expiry. Demo has synthetic Connect/Disconnect only, explicit DEMO, and no browser/network/OTP.

## Task 009 validation

On 2026-10-08, the user completed legitimate sign-in entirely in the official isolated window. Production observed strict successful login and the subsequent exact success route; Settings reached Connected with `SessionValidity.VALIDATED`. The controlled check then clicked the local Disconnect button, verified Not connected, profile disposal, responsive UI and clean process exit 0. Counts were 12 allowed auth/bootstrap requests, two blocked non-auth API attempts and 15 blocked external requests; none of the blocked data was retrieved. Application log records and private stderr bytes were zero. No credential/code/session value, account payload, live SMS screenshot or raw capture was exported.

All 500 backend/service, 128 GUI and 57 Node tests passed (685 total), including rejection/expiry/reconnect/cancel/privacy paths using synthetic data. Editable/wheel packaging, native normal/demo launches, all 63 Python AST parses, TOML/JSON/JavaScript syntax, tracked/untracked whitespace/diff, privacy and all 40 legacy hashes passed. Earlier cancellation/window confusion is resolved by the final single-window check. Hardware server expiry/logout and repeated live reconnect were not forced.

## Deferred work and remaining unknowns

Balances, load, data allowances, promos, account refresh, carrier auto-detection, Smart, persistent sessions, OTP automation and Task 010 remain unimplemented. Server lifetime/renewal, actual expiry timing/server logout, OTP freshness/account binding, alternate site builds and third-party security dependencies are unknown. The likely matcher succeeded on one observed inbox without exporting its template/code, which does not establish universal carrier compatibility. Source changes fail closed until reviewed; external challenges are not bypassed.

These must be investigated rather than guessed.

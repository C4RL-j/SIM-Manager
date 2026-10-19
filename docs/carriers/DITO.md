# DITO Adapter

Status: Task 009 authentication/session lifecycle complete. The separately
authorized Home account reader and shared automatic-refresh/tray presentation
are implemented. The account reader's live validation remains recorded in the
account-data plan. Smart/TNT and other tasks remain deferred.

## Live account data on Home

After the existing strict sign-in proof, the isolated page reuses its own official
request module, without copying cookies/tokens or reconstructing signing. Reviewed
read getters are `/ecare/webs/subs/qrySubsDetail` (GET, one site-owned product ID),
`/ecare/webs/common/configParam` (usage-category configuration), and the two POST
balance getters `/ecare/webs/balance/balInfo` and
`/ecare/webs/balance/balInfo/glSumInfo`. POST is their official read method.
The protected Home/BaseLayout chunks stay blocked so unrelated mount effects,
subscriber/account actions and purchases remain outside this integration.

Load uses Home's `acctResId === 1` principal book. Remaining data and SMS/call
categories use the official usageGL configuration and exact returned `glId`
matches. Detail rows preserve `acctResName`, `formatRealBalance`, returned unit,
`unlimitedFlag` and `expDate`. Aggregate and individual buckets are kept separate;
no totals or dates are synthesized. Resource labels shown under MyDITO's
"My Promo Details" do not establish a commercial offer name. Unsupported fields
stay unavailable rather than being inferred from an unused package-history API.

The page checks subscriber `accNbr` against the current SIM before and after
requests; product/subscriber IDs remain in JavaScript. A mismatched/unverified
number clears data/session. Fresh reads disable the original request client's
cache (`useCache: false`) and bypass browser HTTP cache (`cache: 'no-store'`),
without changing the official getter paths, request bodies or signing. They have
bounded timeouts
and cancellation. The initial refresh follows sign-in. Normal mode then schedules
account refresh every thirty seconds while the inserted DITO profile remains
Connected/Validated; Settings can disable it or select fifteen/thirty/sixty
seconds. Home and tray manual refresh use the same service/read slot. Pending
reads disable the existing actions and show `Refreshing...`.
Temporary failures explicitly report a failed refresh, keep old values marked
stale and retain the original successful-refresh timestamp; root-return/auth expiry
requires Reconnect DITO. Date strings retain reported form/timezone information;
Last updated is the local successful-retrieval time. No private raw response,
number, token or account snapshot enters logs, application files or fixtures.

Verified source/schema, live field presence and limitations are recorded in
`plans/completed/006-dito-account-data.md`; current source inspection does not
claim universal schemas or server-session lifetime.

## Scheduled refresh and rate limits

The shared account scheduler reads only through the existing official page client
and authenticated isolated session. Tray presentation consumes the same normalized
profile/account state as Home, with no second browser, hidden account source or
polling triggered by opening the popup. Router status and SMS retrieval remain
independent. No verified total allowance is currently available; Home and tray
hide their progress components rather than infer percentages from bucket names.

Temporary errors preserve the last successful values marked stale and delay
automatic retries with bounded exponential backoff. HTTP 429 produces a closed
rate-limited outcome; only a normalized `Retry-After` duration crosses the page
boundary. Retry metadata is bounded to one hour, with a sixty-second fallback
when unavailable. Service-level monotonic cooldown and the shared scheduler keep
manual clicks from bypassing a server limit. Successful reads clear backoff;
SIM changes, disconnect and observed expiry stop scheduling for the old account.
These are account-data retries, never automatic sign-in or OTP actions.

Only the three public application preferences persist through Qt settings.
MyDITO sessions, account data, cookies/tokens, phone numbers and codes remain in
memory. Opt-in close-to-tray may keep that existing process/session running while
the main window is hidden; explicit Exit disposes it, and restart still requires
official sign-in. Refresh/tray checks use synthetic sessions and rate-limit
responses; no new live account evidence is implied by this extension.

## Authentication

The [official DITO website](https://dito.ph/) links MyDITO Account to [https://my.dito.ph/](https://my.dito.ph/). The application opens that exact HTTPS origin only after **Home → MyDITO Account → Connect DITO** for the active DITO profile. A dedicated unnamed Qt WebEngine profile is off the record, with memory cache, no persistent cookies/permissions and no access to the user's normal browser profile. Authentication, challenges and consent stay on the official site. SIM Manager does not read input values, handle passwords or copy browser cookies/tokens/storage. Explicit OTP filling is described below. Base/backend imports stay independent of Qt; the desktop extra includes Qt WebEngine through PySide6-Addons.

The browser/page/request policy and source-backed observer live under `carriers/dito/`. `services/accounts.py` publishes neutral opaque `AccountState`; the GUI hosts compact controls and receives closed state only. The observer wraps only the site's existing first-party fetch flow, never initiates requests, and observes strict top-level `loginSuccess === true` from the official login POST **and** the subsequent exact `/pto/home` transition. The transition follows any required user Privacy Statement/Agree action and site-owned session installation. Neither a URL alone nor token/cookie presence is accepted as authentication proof. The observer returns only closed events; no raw response reaches Python/UI.

The default authentication-only request allowlist permits evidenced official manual auth, sign-in SMS/captcha, configuration/legal bootstrap and first-party static assets. The enabled account reader adds only the reviewed getters above. Unrelated customer/account APIs, purchases, password reset, router origins, external analytics/debug scripts and unknown origins stay blocked. Protected BaseLayout/Home script families remain blocked to avoid unrelated bootstrap effects; no account website view is rendered. The original authentication-only handoff passed earlier controlled sign-in; the current reader preserves its strict authentication proof and original login controls.

## Login popup presentation

The compact web viewport keeps its 480×520 base shell, 420×500 base minimum and
88% zoom; the optional native SIM helper adds its own height above it.
Compact shell/card/footer spacing keeps the recognized SMS card's controls and
legal links visible without scrolling at the normal size; manual resizing remains
supported.
The sign-in popup has an optional presentation-only script which centers the
recognized original Sign In with SMS card and hides safe page chrome/marketing.
Known desktop-width wrappers become responsive; footer marketing is hidden only
when it contains no protected controls or legal links. Terms and Privacy remain
accessible, with wrapping instead of horizontal clipping.
It runs in Qt's isolated ApplicationWorld after DOM readiness. The official
inputs, SMS request, sign-in handler, errors, CAPTCHA and consent remain owned by
MyDITO. No values are read, supplied, copied or intercepted by the styling code.
If the card/control structure is unfamiliar or a security/consent surface is
visible, styling is removed and the normal full page is available. Missing or
failed styling also leaves authentication unchanged. Cancel sign-in remains a
native button outside the page. Request policy, authentication observer and
memory-only session behavior are unchanged.

## SIM number and OTP helpers

The native selector shows saved profile name/carrier/number, highlights the
inserted profile and disables others. Copy Number uses only the active DITO
profile and removes exactly one first leading zero without modifying metadata.

Trusted clicks on the original Get SMS Code control start a bounded watch through
the existing read-only inbox worker. The first complete read started after that
click is a baseline; only newly observed likely DITO code content can enable
explicit Fill OTP/Copy OTP. Prior content, reused IDs and changed timestamps do
not make an older code new. Partial/unavailable snapshots cannot establish a
baseline or new candidate; multiple distinct new codes disable assistance.
Watching expires after five minutes. An OTP arriving before the baseline cannot
be proved new and is ignored by this helper; manual entry remains usable.

Fill uses only the original recognized SMS input, its native setter and ordinary
input/change events. It does not read phone/password/code fields, click Sign In,
submit, bypass challenges, or change the auth API. An unfamiliar field, different
mode/route or visible challenge disables filling without touching presentation
fallback. DOM/request and SIM revisions reject stale callbacks; cancellation,
success/rejection and closure clear temporary helper state. Number/OTP clipboard
actions are explicit, clean up only their own unchanged clipboard value and
discard errors without private output. No helper values or messages are written
to application files.

## Evidence and legacy audit

The sanitized source/validation ledger is `tests/fixtures/dito/auth-source-evidence.json`: official URLs, public asset hashes/offsets, classified facts, closed live outcomes and unknowns. It contains no authenticated capture or credential value. Source inspection on 2026-10-08 verified the site's same-origin POST `/ecare/webs/user/login`, strict success field, optional consent, success route, source-only GET logout returning numeric JSON zero, and HTTP 401/`PORTAL-SECURITY` login-required handling. Controlled sign-in verified the strict success/route signal and GUI session establishment; actual server logout/expiry remain source-only/offline evidence. No fixed server lifetime was found.

| Classification | Evidence / disposition |
| --- | --- |
| VERIFIED SOURCE | Legacy official MyDITO URL (`desktop.py:32`) remains linked by DITO. Current official public bundles establish manual SMS/password sign-in, consent and success/expiry handling. Official FAQ documents six-digit SMS authentication. |
| INFERRED | Legacy DITO sender/phrase OTP heuristic, first-match-as-latest, naive 150-second freshness and URL-only success detection. Only the cautious likely-OTP heuristic is retained; no freshness/account binding is claimed. |
| OBSOLETE | Legacy no-submit README conflicts with later automatic submission; missing watcher/cache modules and pywebview/account overlays are excluded. |
| UNSAFE TO REUSE | Persistent WebView profile/saved subscriber numbers, unguarded DOM injection, automatic OTP clipboard/fill/submission, raw watcher/SMS-ID diagnostics and additive long worker shutdown. Legacy remains unchanged/read-only. |

## OTP behavior

`carriers.dito.match_otp(Message)` uses the legacy-evidenced sender `DITO` and six ASCII digits followed by authentication-code wording as a **likely** match. The generic message model/service has no carrier imports or OTP regex. The existing active-profile Copy OTP action consumes user-refreshed Messages results while sign-in is in progress; ambiguous different codes offer none. Selecting a specific message explicitly narrows matching to that message. This profile action adds no polling or freshness/account-binding assumption. The separate popup helper above applies its request-bound baseline and explicit Fill/Copy actions. Neither action submits Sign In. No code is displayed in diagnostic state or logs. Temporary candidate and app-owned clipboard contents are cleared on connection, cancellation, disconnect or shutdown; unrelated clipboard changes are preserved.

During controlled validation the original three-record window showed older messages. The existing getter returned 20 complete messages with one likely match beyond the first three; a 100-record request failed malformed-response normalization. Production Messages now requests a validated 20-record window; raw transport/standalone-client defaults remain three. Native load and Refresh each displayed 20 complete messages, with consistent selection/detail, responsive UI and cleared content on closure. Only counts/status/schema were exported, with no SMS capture or screenshot. This verifies matching for the observed inbox, without proving current-code freshness, account binding, full-inbox paging or newest-first ordering.

## Session lifecycle and storage

States are Not connected, Sign in with DITO, Connected, Session expired and safe connection errors. `SessionValidity.VALIDATED` records the observed successful login; it does not promise continued server validity or a guessed TTL. A rejected login leaves the official form open for another explicit user attempt. No silent sign-in retries occur. Verified auth failures invalidate the session; return to sign-in or a new document after connection conservatively disconnects because its observer context has reset. Reconnect starts a fresh isolated profile. Cancel and final application exit revoke generations before browser disposal, so late callbacks cannot restore a session.

**Disconnect** is local disposal of this application's entire isolated profile/page, including its site-owned session storage; it does not claim remote server revocation. The source-evidenced server logout is not automatically called. Session, browser cookies/tokens, user inputs and temporary OTPs are never persisted to config, fixtures, captures or credential storage. Restart requires sign-in again. Browser memory isolation and dropping references do not promise forensic erasure of process memory or OS paging.

Site JavaScript console output is discarded. Exceptions, navigation/loading metadata and service errors never export raw text, URLs with identifiers, cookies/tokens, passwords, OTPs, SIM identifiers or SMS content. Unknown schemes/popups/downloads/file selection/permissions, certificate exceptions and unsafe external debug/browser flags are rejected. An initial page load has a 30-second limit and probes have a 5-second limit; user sign-in has no invented inactivity expiry. Demo has synthetic Connect/Disconnect only, explicit DEMO, and no browser/network/OTP.

## Task 009 validation

On 2026-10-08, the user completed legitimate sign-in entirely in the official isolated window. Production observed strict successful login and the subsequent exact success route; Settings reached Connected with `SessionValidity.VALIDATED`. The controlled check then clicked the local Disconnect button, verified Not connected, profile disposal, responsive UI and clean process exit 0. Counts were 12 allowed auth/bootstrap requests, two blocked non-auth API attempts and 15 blocked external requests; none of the blocked data was retrieved. Application log records and private stderr bytes were zero. No credential/code/session value, account payload, live SMS screenshot or raw capture was exported.

All 500 backend/service, 128 GUI and 57 Node tests passed (685 total), including rejection/expiry/reconnect/cancel/privacy paths using synthetic data. Editable/wheel packaging, native normal/demo launches, all 63 Python AST parses, TOML/JSON/JavaScript syntax, tracked/untracked whitespace/diff, privacy and all 40 legacy hashes passed. Earlier cancellation/window confusion is resolved by the final single-window check. Hardware server expiry/logout and repeated live reconnect were not forced.

## Deferred work and remaining unknowns

Carrier auto-detection, Smart, persistent MyDITO sessions, automatic authentication/OTP submission and other roadmap tasks remain outside this integration. The verified reader exposes only reported balances/allowances/resource details; a commercial promo identity or total allowance cannot be inferred from those labels. Server lifetime/renewal, actual expiry timing/server logout, OTP freshness/account binding, alternate site builds and third-party security dependencies are unknown. The likely matcher succeeded on one observed inbox without exporting its template/code, which does not establish universal carrier compatibility. Source changes fail closed until reviewed; external challenges are not bypassed.

These must be investigated rather than guessed.

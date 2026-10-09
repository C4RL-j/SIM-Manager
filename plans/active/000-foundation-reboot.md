# 000 — SIM Manager foundation reboot

Date: 2026-10-07

Updated: 2026-10-08 (Asia/Irkutsk)

Status: Audit complete; Tasks 001–009 and Task 006.1 complete within approved scopes; Task 010 not started

Scope: Historical audit, transport foundation, read-only D2 hardware/telemetry discovery, normalized device state, native desktop shell and UI polish, read-only Messages inbox, isolated DITO authentication/session lifecycle, and future migration plan

## Decision

Keep the existing Python D2 Telnet/UBus SMS transport as the migration starting point. Copy it into `sim-manager/` with offline characterization tests before changing its behavior. Build small device, carrier, service, storage, and UI boundaries around the code that is actually present. Do not transplant the legacy desktop controller or rewrite the router protocol to establish those boundaries.

`old/` remains read-only reference material. “Remove” below means exclude from the new application, never delete or edit the reference tree. The original audit created this plan only. The approved Task 001 adds a minimal package and offline transport characterization without repairing legacy imports, installing dependencies, contacting hardware, or implementing features.

Task 002 completed narrow D2 transport hardening with offline regression tests. It changed the new copy after characterization while preserving the working UBus wire command. It did not implement SMS normalization, carrier/account features, hardware probing, SIM/network/signal detection, GUI work, or Task 003.

Task 003 completed observational D2 hardware discovery with a manually invoked development probe and a capability report. Read-only safety was established before each fixed query was executed. At its completion, production detection/normalization, carrier/account integration, and GUI work were unstarted. Never alter router configuration or guess AT/vendor commands.

Task 004 completed discovery of read-only cellular telemetry used by the firmware/admin UI. Source inspection established seven GETs; the user returned a sanitized authenticated report from the legitimate Brave session. Raw labels and field types are verified within the report's privacy limits; units, broader state meanings, carrier identity, and modem firmware revision remain unverified. Its discovery scope did not authorize production/carrier logic.

Task 005 completed the Device and normalized model boundary only: immutable carrier-neutral state models, defensive D2 response normalization, and one read-only status snapshot client over the seven verified endpoints. Authentication remains an explicit injected session boundary: without a session, the client returns unknown/authentication-required state with no I/O. No Brave bridge, credential transfer, carrier mapping, GUI/storage/account feature, or Task 006 work was implemented.

Task 006 completed the first native Windows desktop shell using PySide6 Qt Widgets. Overview, Messages, and Settings consume a service/view-model derived from the existing `DeviceState` snapshot; the user's conceptual `DeviceSnapshot` did not require renaming the backend model. Default production mode preserves the missing-authentication/no-I/O state. Explicit `--demo` uses only sanitized Task 004 fixture-derived state and labels the window DEMO; production never substitutes fixture data. No carrier login/account integration, authenticated-session bridge, SMS send/delete, configuration persistence/editing, or Task 007 was implemented.

Earlier audit references to pywebview/WebView2 describe legacy behavior and a possible future carrier-account browser surface. They do not mandate a framework for the approved native shell. PySide6 Qt Widgets is the Task 006 desktop framework; any future browser integration requires its own scope and remains separate from this UI.

The new application repository is `C:\PROJECTs\SIM-manager_workspace\sim-manager`. Git must be initialized inside `sim-manager/` only, never at the workspace root. `../old/D2-desktop/` must never be added to the new repository. Preserve the legacy tree and verify its file list and SHA-256 hashes before/after extraction.

Initial implementation targets D2 and DITO. Smart/TNT/Smart Bro must fit the same interfaces later, but Smart features are deferred to roadmap Phase 4. SMS sending was inspected for reuse; it is absent and is not a Phase 1 requirement in the current roadmap.

## Sources and audit boundaries

Read `sim-manager/AGENTS.md` and all six files under `sim-manager/docs/`: `PROJECT.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `WORKFLOW.md`, `carriers/DITO.md`, and `carriers/SMART.md`. At the original audit, `WORKFLOW.md` and `carriers/SMART.md` were empty and workflow rules came from `AGENTS.md`. Task 001 adds reproducible offline commands to `WORKFLOW.md` and the current package boundary to `ARCHITECTURE.md`.

Inspected the entire supplied file tree, all 20 legacy Python source modules, all 15 test modules, the README, three batch launchers, and PyInstaller specification. References such as `old/D2-desktop/router.py:210` use paths relative to the workspace root and line numbers from this snapshot.

Findings describe checked-in code, not live hardware or the current MyDITO website. The legacy README calls the router path working, but this audit did not verify a router connection, modem firmware, carrier session, DOM behavior, or packaged executable. Tests referencing missing modules describe intended behavior rather than supplied implementations.

## 1. Repository map at the original audit

```text
SIM-manager_workspace/
├── old/
│   └── D2-desktop/                 # 40 files; read-only reference
│       ├── app.py                  # delegates to desktop.main
│       ├── desktop.py              # pywebview/WebView2 controller, 1,981 lines
│       ├── home_dashboard.py       # HOME model, HTML/CSS/JS overlay
│       ├── router.py               # D2 Telnet/UBus inbox transport
│       ├── otp.py                  # DITO OTP extraction and timestamps
│       ├── dito_otp_helper.py       # standalone earlier router/OTP prototype
│       ├── legacy_app.py           # earlier Tkinter OTP GUI
│       ├── dashboard_inspector.py  # MyDITO DOM heuristics and reports
│       ├── account_snapshot.py     # models, parsers, extraction, formatting
│       ├── login_automation.py     # MyDITO phone entry and Continue automation
│       ├── mydito_focus.py         # MyDITO login/OTP focus and scrolling
│       ├── otp_page_detection.py   # OTP DOM detection and state machine
│       ├── otp_autofill.py          # single/segmented OTP entry
│       ├── otp_submit.py            # submission and authentication heuristics
│       ├── auth_number.py           # login state constants
│       ├── user_settings.py         # saved numbers and JSON persistence
│       ├── saved_number_dialog.py   # DITO-specific Tkinter modal dialog
│       ├── dashboard_formatting.py  # quantities, percentages, ages, expiry
│       ├── clipboard_privacy.py     # conditional cleanup predicate
│       ├── windows_clipboard.py     # Win32 Unicode clipboard operations
│       ├── tests/                   # 15 unittest files; 215 test methods
│       ├── README.txt
│       ├── DITO Desktop.spec
│       └── run_dito_*.bat           # three launchers
└── sim-manager/
    ├── AGENTS.md
    ├── docs/
    │   ├── PROJECT.md
    │   ├── ARCHITECTURE.md          # high-level layer diagram only
    │   ├── ROADMAP.md
    │   ├── WORKFLOW.md             # empty
    │   └── carriers/
    │       ├── DITO.md
    │       └── SMART.md            # empty
    ├── src/                        # empty at audit start
    └── plans/
        ├── active/                 # this plan added by the audit
        └── completed/              # empty
```

There was no root `AGENTS.md` or root `docs/`; the project instructions were under `sim-manager/`. No Git metadata, dependency manifest, lockfile, CI configuration, or reproducible installation instructions were supplied. At that time `git status --short` failed because the workspace was not a Git repository. `watcher.py` and `account_cache.py` were absent everywhere in the supplied tree despite imports and tests. This historical map and inventory are retained as audit evidence; the Task 001 additions are listed in section 7.

## 2. Capability inventory: existing code versus gaps

| Requested area | Supplied implementation and evidence | Reuse decision / missing work |
| --- | --- | --- |
| D2 router communication | `router.py:45` Telnet negotiation; `:87` banner reads; `:107` completion marker; `:140` UBus command; `:150` shell JSON extraction; `:210` socket orchestration; error types at `:25`. Defaults to `192.168.1.1:2323`. | Keep as the device transport seed. Expects a pre-existing direct shell; no discovery, model/firmware verification, HTTP client, or Telnet authentication implementation. |
| Quectel modem communication | No Quectel driver, AT transport, serial-port code, modem identification, or EG060-specific parser exists. | The documented EG060V-EAAA target is not an implemented capability. First investigate what D2 exposes through its existing `cped` service; introduce direct modem transport only if evidenced and necessary. |
| SIM detection | No physical SIM state, PIN state, ICCID/IMSI, or installed-SIM identification query exists. | Build from verified device responses later. Saved phone numbers and a DITO SMS sender do not detect the inserted SIM. |
| Carrier detection | No device-backed carrier recognition exists. | Build normalized carrier recognition from reliable device/SIM evidence. Phone-number format, router branding, SMS sender, and a MyDITO account session are insufficient proof. |
| Network information | No registration, operator, roaming, RAT, band, cell, or network query exists. | New device capability after discovery; represent unavailable fields explicitly. |
| Signal information | No RSSI, RSRP, RSRQ, SINR, or signal-strength query exists. Search hits for “signal” are browser heuristics, not modem measurements. | New device capability with verified units, missing-value semantics, and fixtures. |
| SMS reading | `router.py:140` issues `sms.get.inboxdata` using `StartPos:0` and default `ReadNum:3`; `:196` selects a success envelope. | Keep wire command and parsing knowledge. Full inbox paging, normalized messages, and robust payload validation are missing. Newest-first ordering is assumed rather than established. |
| SMS sending | No send command, recipient/body encoding, delivery state, or send UI exists. No delete or explicit mark-read operation either. | Build only in a later scoped task after command/encoding discovery. Do not invent UBus or AT commands. |
| OTP detection | `otp.py:14` `OTPInfo`; `:55` timestamp parsing; `:77` `find_latest_dito_otp`; tests in `test_otp.py`. | Keep metadata/freshness concepts. Move the DITO sender/exact English phrase rule into the DITO adapter; normalize device SMS separately. |
| OTP watching | Desktop/Tkinter code imports `watcher`; `tests/test_watcher.py` expects injected fetchers, freshness, new-message identity, timeout, and error handling. Callers pass `stop_event` for cancellation, which those watcher tests do not cover. | Implementation is missing. Recover from an authoritative source if available; otherwise implement a service later using reviewed tests as specifications, adding cancellation coverage. |
| Account information | `account_snapshot.py:169` interprets MyDITO DOM reports for main data, buckets, calls, and expiry. | Reuse parsers behind DITO. Load balance, remaining texts, and rewards are always `None` at `:215`; there is no complete normalized active-promo API. |
| UI | WebView2 shell, HOME allowance cards, number picker, status/age badges, progress bars, expiry warnings, native hotkeys, and Tkinter dialogs. | Reuse selected widgets/styles/model ideas. Current UI is DITO-specific and shares the remote carrier DOM. Build the neutral application shell separately. |
| Configuration/storage | `user_settings.py` provides versioned JSON, local app-data paths, validation, saved-number operations, and atomic replacement. Desktop configures a persistent WebView2 profile. | Reuse mechanisms after schema/identity fixes. Router endpoint configuration, safe account-scoped caching, explicit logout, and session isolation are absent. `account_cache.py` is missing. |

## 3. File disposition

| Keep or refactor | Destination / reason |
| --- | --- |
| `router.py` | Copy into the new D2 device package first. Preserve command construction, timing, echo-marker workaround, and public error semantics until characterized. No DITO dependency is needed for inbox transport. |
| `otp.py` | Split D2 payload decoding from carrier matching. Retain metadata and timestamp utilities with explicit clock policy; place DITO matching in `carriers/dito/`. |
| `user_settings.py` | Retain JSON validation and atomic writes. Extract generic Philippine phone normalization/masking; keep MyDITO login-number conversion inside DITO. Replace dual saved-number/SIM schema before import. |
| `account_snapshot.py` | Separate neutral result models from MyDITO row heuristics and browser polling. Preserve unknown/partial/error distinctions; add account binding and provenance before caching. |
| `dashboard_formatting.py` | Reuse small pure formatting helpers after correcting unit/time assumptions. Move carrier-specific interpretation out of shared presentation. |
| `clipboard_privacy.py`, `windows_clipboard.py` | Keep as optional Windows platform utilities; fix conditional-clear race before using cleanup in the new app. |
| `home_dashboard.py` | Reuse allowance cards, status/age/expiry presentation and view-model ideas against normalized service results. Replace injection into the remote document and DITO labels/mailboxes. |
| `desktop.py` | Extract limited platform/browser setup (`NativeHotkey`, app-data path, TLS/debug settings). Replace the monolithic orchestration with small services and a thin UI controller. |
| `dashboard_inspector.py`, `login_automation.py`, `mydito_focus.py`, `otp_page_detection.py`, `otp_autofill.py`, `otp_submit.py`, `auth_number.py` | Keep as Phase 2 DITO reference and selective reuse candidates. They belong behind the DITO integration/session boundary. Their heuristics are not a validated current carrier API. |
| `saved_number_dialog.py` | Retain validated user-intent/result patterns if useful. Adapt copy and event-loop integration only when settings UI is implemented. |
| Existing tests | Migrate relevant behavior tests with the code they protect. Decouple pure tests from desktop/cache imports; distinguish normalizer tests and script-string assertions from actual browser integration tests. |

Exclude `dito_otp_helper.py`, `legacy_app.py`, old `app.py`, old batch launchers, and the unchanged `DITO Desktop.spec` from the new runtime. They duplicate flows, target old branding/entry points, or assume unmanaged Python on PATH. Keep their files as reference. Use the packaging recipe only as later build guidance. Do not copy raw-output debugging, automatic clipboard copy from the standalone helper, a global legacy account cache, or DITO-specific HOME/MYDITO navigation into the new generic UI.

## 4. Technical debt and risky assumptions

### Resolve before presenting a reliable migrated device path

1. **Incomplete legacy runtime.** `desktop.py:13`, `:16`, `:28` imports `webview`, missing `account_cache`, and missing `watcher`. Installing pywebview alone cannot restore this snapshot. Do not use fake replacement modules to claim the legacy suite or application works.
2. **Direct-shell dependency.** `router.py:210` assumes a reachable unencrypted Telnet shell on port 2323 and rejects a login prompt. A TCP connection does not establish D2 model identity or modem/SIM health. Treat shell availability as a supported configuration requirement; do not enable shells, alter firmware, bypass authentication, or guess credentials as part of migration.
3. **Fragmented Telnet negotiation.** `handle_telnet_bytes` at `router.py:45` has no state between receives. A split IAC/option sequence is lost; subnegotiation is not fully handled. An offline fake-socket probe confirmed split negotiation bytes can leak into payload. Add characterization and regression cases before a narrow stateful-parser fix.
4. **Echo/marker and timeout assumptions.** `router.py:107` requires two occurrences of a static marker because the shell echoes commands. Echo-disabled shells can time out after a successful command; disconnects can be reported as timeouts. Reads use wall-clock deadlines and repeatedly rescan unbounded accumulated output. Characterize echo, split markers, disconnects, truncation, and timeout boundaries; then introduce monotonic deadlines, bounded output, and explicit completion/error handling where justified.
5. **Input and response validation.** `build_sms_command` at `router.py:140` interpolates `read_num` and `marker`; future configurable inputs require validation and safe quoting. `get_sms_response` at `:196` validates only `code`, `msg`, and presence of `data`, not its shape. `otp.py:100` calls `.strip()` on unchecked body/sender values. Malformed data must produce sanitized typed failures rather than crash polling. Do not expose a generic arbitrary-shell-command API.
6. **Limited inbox window and OTP clock policy.** The first match in three records is called “latest” without sorting (`otp.py:77`). Freshness uses a fixed 150-second threshold and naive host-local time (`:10`, `:25`). Router/SMS time zone, clock skew, missing dates, ID reuse, SIM changes, and actual OTP expiration are unverified. Keep expiry policy configurable within the service/carrier boundary and define behavior for unknown times.

### Resolve before account/UI/storage migration

7. **False availability.** `desktop.py:229` passes `router_status="Available"` without probing. The new UI must reflect a real device result and distinguish disconnected, unavailable, unsupported, and unknown states.
8. **Remote DOM is also the application surface.** `home_dashboard.py:261` embeds the local model, including full saved numbers from `desktop.py:244`, into JavaScript; `home_dashboard.py:486` appends the app shell to the carrier document. Remote-page scripts can read those entries and change the `window.__ditoDesktop*` request flags (`:106`). Keep app UI/data on a local app-owned surface and the carrier browser session on a separate trusted surface. Preserve `js_api=None` for remote content (`desktop.py:1960`).
9. **Missing origin checks and DOM ambiguity.** Browser automation operates on the active document without an official-origin allowlist. OTP field selection uses first-match/first-six heuristics; `otp_autofill.py:412` can retain an earlier success after verification reports failure. Before Phase 2 reuse, enforce trusted origin/navigation state, unique intended fields, verification, and cancellation on navigation/account changes. Keep manual authentication as a functional fallback; never automate around CAPTCHA/security challenges.
10. **Possible detection feedback.** `dashboard_inspector.py:141` scans global visible document elements without excluding the injected app overlay. Its dashboard evidence at `:170` may therefore include locally rendered cached account text. This is a static risk, not a reproduced live failure. Isolating the UI prevents this feedback; browser fixtures must ensure app-created text cannot establish authentication or fresh account data.
11. **Session persistence is not session lifecycle.** `desktop.py:1855` and `:1970` provide a persistent local WebView2 profile. There is no established logout/invalidation implementation, account-separated profile design, or verified session lifetime. A cached snapshot with `authenticated=True` must never establish a current logged-in state. Use legitimate user-authenticated carrier sessions; keep browser-managed credentials outside JSON settings and the repository.
12. **Saved account entries are not detected SIMs.** `UserSettings.remembered_number` returns the first saved entry even if `active_sim_id` selects another (`user_settings.py:48`). Stored `sims` and `saved_numbers` duplicate truth (`:202`); deletion preserves nondefault SIM entries (`:435`) and reload can reconstruct deleted numbers (`:249`). “Remember off” preserves serialized numbers (`:409`). Define selection, disable-remember, forget, and delete separately; use one canonical schema. Do not silently import old settings or overwrite the old app-data directory.
13. **Account/cache identity is absent.** `AccountSnapshot` at `account_snapshot.py:68` has no carrier/account/SIM binding, and the controller uses one default cache path (`desktop.py:161`). A chosen MyDITO account may differ from the SIM in the router. Bind future cached account data to its actual carrier account/profile; keep device SIM identity separate. On SIM/account change, cancel obsolete work and invalidate the relevant view. Do not attach old global balances to a newly detected SIM.
14. **Incomplete and potentially overlapping allowances.** `account_snapshot.py:201` requires main data, buckets, and calls for success; valid data-only accounts can remain partial. Main-data matching recognizes all/open-access labels (`:276`) while bucket exclusion only recognizes mobile-data labels (`:290`), risking overlapping displays. Load/text fields are unimplemented. Preserve carrier categories and unknowns; do not sum overlapping buckets or fabricate zero balances/promos.
15. **Time/unit semantics.** `account_snapshot.py:82` produces naive English-display expiry dates while capture times are aware UTC; `dashboard_formatting.py:99` strips or attaches timezone information during comparisons. Data parsing permits arbitrary alphabetic units, and formatting assumes MB/GB with a 1024 conversion (`dashboard_formatting.py:10`). Establish observed carrier units and time zone before computing percentages, expiry, or totals; preserve source display strings where interpretation is uncertain.
16. **Concurrency, repeated rendering, and clipboard ownership.** `DesktopController` has multiple threads, shared mutable authentication state, and browser locks; shutdown joins have shorter limits than possible router operations (`desktop.py:1813`). Its polling loop rerenders the overlay every 0.75 seconds (`desktop.py:436`), rebuilding contents (`home_dashboard.py:527`) even without data changes. Extract bounded, cancellable service operations, serialize browser work, and render on relevant state changes; prevent results from prior SIM/account/navigation generations updating a new view. Clipboard cleanup reads and clears in separate opens (`windows_clipboard.py:128`), so a user clipboard update can be erased between them. Compare/clear under one clipboard lock before reuse.
17. **Documentation/build/coverage gaps.** README describes older phases and says account data is not cached, while `desktop.py:1535` calls cache saving. No direct checked-in router transport tests or hardware fixtures exist. Most browser tests normalize results or inspect script strings without executing JavaScript against a real DOM. No reproducible dependency/build setup exists. Preserve useful tests while documenting their limits; avoid another broad browser-helper framework while core behavior is still uncertain.

## 5. Comparison with `docs/ARCHITECTURE.md`

The documented stack is UI → Services → Carrier abstraction (DITO/Smart) → Device abstraction (D2/Quectel), with information flowing upward. `AGENTS.md` clarifies that device behavior must not leak into carrier adapters, carrier behavior must not leak into UI, and the UI consumes normalized operations such as `get_carrier()`, `get_signal()`, `get_messages()`, `get_data_balance()`, `get_load_balance()`, and `get_active_promos()`.

| Intended boundary | Current structure | Migration alignment |
| --- | --- | --- |
| Device | `router.py` is already largely carrier-independent, but only exposes raw SMS envelopes. The older helper duplicates it. | Keep one D2 implementation; own Telnet, UBus, device payload parsing, and hardware capability errors here. |
| Carrier | DITO behavior is spread across OTP parsing, settings, browser scripts, account extraction, controller, and UI. No carrier abstraction exists. | Place DITO OTP/content/account interpretation and official-site integration behind one adapter boundary consuming normalized device/service inputs. |
| Services | Polling, login sequencing, cancellation, cache updates, clipboard actions, and view changes live in `DesktopController`; watcher/cache implementations are missing. | Extract small orchestration services with injected device/carrier dependencies and clear state/results. |
| UI | Desktop and HOME directly know MyDITO DOM, account parser/cache types, saved identities, and automatic login actions. UI is injected into the carrier page. | Build local Overview/Data/Messages/Settings views consuming service results. Labels and available actions follow adapter capabilities. |
| Storage/shared models | Versioned settings exist, but identifiers, sources, timestamps, and schema ownership are inconsistent. | Keep storage independent of browser/carrier parsing; share small neutral result types with provenance and explicit unknowns. |

The architecture document specifies no package layout or detailed call graph. The proposed layout below implements its boundaries without changing the architecture in this task. Clarify during foundation implementation that generic device reads (signal/SMS/network) can be orchestrated by services without adding carrier-specific wrappers; carrier adapters consume normalized messages when their own rules require them. Carrier account results remain separate from router information and locally measured usage.

## 6. Proposed target layout — future implementation only

```text
sim-manager/
├── pyproject.toml                  # Python package, dependencies, tooling
├── src/sim_manager/
│   ├── __init__.py
│   ├── main.py                     # composition/startup only
│   ├── models.py                   # small normalized results and statuses
│   ├── config.py                   # endpoint and polling configuration
│   ├── devices/
│   │   ├── base.py                 # minimal contract actually needed
│   │   └── d2/
│   │       ├── router.py           # first copy of legacy transport
│   │       └── sms.py              # verified envelope/message normalization
│   ├── carriers/
│   │   ├── base.py                 # carrier identity/capability contract
│   │   └── dito/
│   │       ├── adapter.py
│   │       ├── otp.py
│   │       └── mydito/             # browser/account integration, Phase 2
│   ├── services/                   # device refresh, messages, OTP, accounts
│   ├── storage/                    # settings; account cache when needed
│   ├── platform/                   # optional Win32 clipboard/hotkeys
│   └── ui/                         # local, carrier-independent presentation
├── tests/                          # focused unit/contract/browser tests
├── docs/
└── plans/
```

Create folders/modules only when their task needs them. At the original audit, no separate Quectel driver, Smart implementation, plugin registry, event bus, database, or new UI framework was justified by the audit alone. Selective pywebview/WebView2 reuse was proposed for future authenticated account work rather than device-only startup. Task 006 later explicitly approves PySide6 Qt Widgets for the native shell; this historical browser proposal is not a framework mandate. Evaluate startup/memory/package size when any future browser integration is runnable.

Normalized results should carry explicit status, observation time, units where applicable, and source (`device`, `carrier`, or `local_measurement`). Account results also need account/profile binding and freshness; cache origin is a presentation/storage state, not proof of authentication. Unknown/unsupported/failed values must stay distinct from valid zero values. Choose small typed records and only the contracts needed by the first implementation, rather than designing every future feature upfront.

Approved requirements beyond Task 001:

- Shared OTP watcher services consume a carrier-provided matcher/predicate. They must not import DITO OTP logic directly.
- Carrier detection uses cellular/SIM/operator information, not router branding. A Smart-branded D2 does not establish that the inserted SIM uses Smart.
- Normalized allowance models support data-only products and non-expiring products; calls/text allowances and expiry must not be mandatory evidence of a valid account result.
- Task 002 transport hardening implements cooperative cancellation and monotonic deadlines, verified offline. The preceding watcher, carrier-detection, and allowance requirements remain future work.

Diagnostic logs and exception output must mask or omit full phone numbers/MSISDNs, IMSIs, ICCIDs, OTPs, SMS bodies containing sensitive information, authentication cookies, tokens, and passwords. Tests and fixtures use synthetic values. This documentation rule does not authorize wire-protocol changes during the Task 001 extraction.

## 7. Safest staged migration

### Task 001 — package scaffold and preserve the D2 SMS transport

**Complete and verified.** Affected layers: device, minimal project configuration, documentation, and tests. The minimal Python package and offline characterization suite are in place. `old/D2-desktop/router.py` was copied byte-for-byte into `src/sim_manager/devices/d2/router.py`, preserving its existing call signature/defaults, UBus command, socket pacing, marker workaround, exception classes, and response-selection behavior. The old source remains untouched and is never imported at runtime by the new package.

Task 001 creates only the `sim_manager`, `devices`, and `devices/d2` package namespaces, the preserved `devices/d2/router.py`, a standard-library offline test suite, and minimal project metadata/documentation. `pyproject.toml` uses setuptools, requires Python 3.11 or later, and declares no runtime dependencies. `README.md` and `.gitignore` support using this baseline; there is no application entry point, GUI/browser dependency, carrier/account implementation, SIM/signal detection, or hardware probing.

Acceptance criteria:

- Package imports and test discovery work independently of `old/`, MyDITO, missing watcher/cache modules, and a browser dependency.
- Synthetic fake-socket transcripts cover the exact inbox command, Telnet refusals/escaped IAC, echoed command plus final marker, fragmented payload/marker, nested/stringified JSON with escaped braces, empty/malformed response, login prompt, refusal, connect/response timeout, and early disconnect.
- Known weaknesses are documented explicitly; do not bless broken negotiation or unvalidated payload behavior as desired permanent contracts. Add regressions with the focused fixes in Task 002 rather than silently changing extraction semantics.
- Tests exercise the whole fetch/error path with injected or mocked sockets and clock; they do not contact hardware or record real SMS, OTPs, SIM identifiers, credentials, or raw account data.
- Review the new files against the legacy copy. No feature UI, carrier login, Smart code, modem commands, or broad abstractions enter this task.

Run from `sim-manager/` without installation:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -B -m unittest discover -s tests -v
```

Task 001 test results, legacy-copy comparison, hash verification, diff review, and Git status are recorded in section 8. Its unchanged-copy guarantee applies to that historical baseline; Task 002 intentionally hardens the new copy only.

### Task 002 — narrowly harden transport

**Complete and verified offline.** Affected layers: D2 transport, standard-library offline tests, and documentation. Preserve the default endpoint (`192.168.1.1:2323`), default three-record read, exact `build_sms_command` output (including UBus quoting and CRLF), and fixed historical marker `__DITO_HELPER_END_91F7__`. No hardware/network probing is authorized in this task.

Implementation decisions:

- Keep the five existing positional arguments of `fetch_sms_response`; add keyword-only `stop_event` and `max_response_bytes`, defaulting to a 1 MiB raw-wire limit per read phase. The banner, wake-up read, and command response each have their own limit, including Telnet control bytes.
- Use monotonic deadlines and short receive/send polls: up to 0.5 seconds normally and 0.1 seconds when a stop event is supplied. Preserve the legacy 0.5-second idle wait for banner/wake-up reads within their respective 0.7/0.25-second phase deadlines; short cancellation polls do not end those reads prematurely. Cancellation is cooperative and raises `RouterCancelledError`; check it around I/O and parsing.
- Run the existing `socket.create_connection` call/arguments in a daemon worker. The caller polls at most every 0.05 seconds to honor its monotonic connection deadline or cancellation. Abandonment closes a socket that arrives later and requires no blocking join. The OS DNS call itself remains uninterruptible; repeated abandoned DNS calls can temporarily accumulate daemon workers. This is an explicit residual resource risk, not a claim that DNS is forcibly cancelled.
- Keep one stateful Telnet decoder across banner, wake-up, and response reads. Preserve option-refusal behavior while handling fragmented IAC/option sequences, escaped IAC, and subnegotiation through `IAC SE` without leaking control bytes.
- Accept a completed, terminated, standalone marker line with shell echo enabled or disabled. Marker text inside command echoes or JSON strings must not complete the response. A chunk ending at marker text alone is insufficient evidence of a completed line. Stop response processing at that line; trailing JSON and Telnet bytes in the same receive cannot alter the result or trigger negotiation replies.
- Bound raw wire accumulation and check deadlines during parsing. Use generic sanitized error messages and suppress raw exception chains. EOF/reset becomes `RouterDisconnectedError`, a subclass of `RouterConnectionError`, rather than a misleading response timeout.
- Keep the public JSON extraction helper's nested-object behavior. SMS response selection prefers successful outer envelopes and allows transparent-wrapper fallback only when no top-level object has both `code` and `msg`. Wrapper traversal stops at any envelope with both fields, including an error or incomplete envelope; nested SMS content cannot override it. Skip malformed balanced outer objects whole and stop at unclosed outer objects, preventing nested success promotion in both cases.

Intentionally preserved quirks:

- `data` remains unnormalized and loosely validated; stringified data remains a string. This task does not introduce SMS records, timestamps, inbox ordering/paging, or a new payload schema.
- The last successful eligible envelope can still be selected ahead of a later error envelope.
- The exact historical command, static marker, default endpoint/count, and direct-shell requirement remain. This task does not implement Telnet authentication or confirm the device model/firmware.
- Telnet option-refusal writes remain best effort; their socket errors are swallowed as in the baseline. Cancellation and deadline checks around each reply still bound processing.

Offline regressions must cover fragmented negotiation/subnegotiation, completion with echo on/off, false or fragmented markers, raw-wire caps, monotonic deadlines, cancellation including pending connection setup and cleanup, disconnect classification, response selection, and diagnostic privacy. Preserve successful legacy command/pacing/JSON coverage while updating tests whose former defect is intentionally fixed. Final counts and verification evidence belong in section 8.

At Task 002 completion, the direct shell, `cped` SMS command, line termination, fixed marker, and supported payload variants remained unverified hardware assumptions. Task 003 later confirmed the default direct shell and standalone-line framing for discovery queries, but did not read SMS or verify the historical SMS marker/payload forms. Balanced shell noise can be skipped, but an unclosed leading brace prevents safe resynchronization and causes response rejection instead of nested success promotion. Compatibility with such router output remains an assumption. The daemon worker cannot interrupt the underlying resolver; callers must not create unbounded retries around abandoned hostname lookups.

Deferred beyond Task 002: validated endpoint settings/configuration, message normalization/IDs/timestamps, stronger payload-schema validation, full-inbox ordering/paging, and watcher/cache recovery or implementation. Check authoritative sources for the missing watcher/cache modules before rebuilding their behavior in a later task. These production changes and all carrier/UI work remain unstarted.

### Task 003 — establish device capabilities with evidence

**Complete within the approved discovery scope.** Targeted read-only inspection investigated available SIM/network/radio/WAN/modem sources without requiring every field to exist or implementing the final device/carrier system. Production package code and its original tests were unchanged in Task 003. The separately approved Task 004 is scoped below.

`tools/d2_discovery.py` is a manual development-only probe. It reuses the existing private transport helpers without adding a production arbitrary-command API. Fixed reviewed commands, an 8-second query deadline, 256 KiB per-read-phase raw-wire limits, literal-IP hosts, and Ctrl+C cooperative cancellation bound its scope. Normal console output allows only reviewed metadata and omits unknown/sensitive values. Optional raw responses require `--capture-raw` and stay under the ignored `artifacts/d2-private/` directory; that flag has not been used.

All 18 fixed query types were manually executed; the complete E01–E18 ledger, exact commands, read-only basis, exit status, masked response shapes, and field inventory are in [D2-HARDWARE-CAPABILITIES.md](../../docs/devices/D2-HARDWARE-CAPABILITIES.md). Results:

- **VERIFIED:** default direct shell, UBus help/object/schema metadata, `DISTRIB_ID=OpenWrt`, and USB `1-2` descriptors `2c7c:6004`, manufacturer `Quectel`, model `EG060V-EAAA`.
- **VERIFIED:** host IPv4/IPv6 addresses, one default route per family bound to that USB module's network interface, and three IPv4 resolver entries. Addresses/gateways and unknown interface names are masked or omitted. These observations establish kernel configuration, not registration, cellular address assignment, PDP family, DNS provenance, or Internet health.
- **NOT FOUND:** a verified safe cellular getter in the inspected UBus schema, selected web source files, and static getter/name searches. Method names and field references alone never establish read-only vendor semantics or absent hardware capabilities.
- **VERIFIED text only:** static references to operator/MNC/RSSI/EARFCN/APN/IP fields prove neither runtime values nor a safe getter. Their implications are too weak for an INFERRED runtime-field rating and must not become production behavior.
- **UNTESTED:** SIM present/ready/PIN and identities, operator/PLMN/MCC-MNC/registration/roaming/RAT, band/EARFCN/cell/PCI/signal metrics, active APN/PDP/connection health, cellular IP assignment, modem firmware revision, and hardware-reported router model/exact firmware. The filtered APN configuration read exited 2; failed access does not establish APN absence.

The default shell and terminated-line framing worked without production transport changes. An initial sandbox connection failure was followed by successful authorized network access. No cellular vendor getter, SMS query/read/send/delete, AT command, configuration write, restart, reconnect, reboot, or router installation occurred. No raw-capture flag was used. No actual cellular identifier was observed, so DITO cannot yet be distinguished reliably from Smart; router branding/module identity/MAC/SSID are not substitutes.

Preserved limits and future validation: the binding query assumes a single default route per family, as observed; multiple defaults can yield inconclusive false flags. Static-source scans are bounded and privacy-filtered, not an exhaustive firmware audit. Additional firmware-evidenced getters, units/status semantics, SIM states, firmware variants, cellular assignment, and SMS-specific marker/payload behavior still require separately authorized validation. The probe's private-helper reuse is development-only; no arbitrary production shell API or neutral production models were added.

Future work must retain VERIFIED / INFERRED / NOT FOUND / UNTESTED classifications and distinguish values from units/status interpretation. Keep router reachability, SIM readiness, and registration separate. Carrier interpretation belongs outside `devices/d2/` and must use cellular/SIM/operator evidence. No configuration change or guessed AT/vendor query is authorized by this plan update.

### Task 004 — verify firmware/admin-UI cellular telemetry

**Complete within approved discovery scope; limitations retained.** Identify and verify read-only telemetry interfaces used by the D2's own firmware/admin UI. Investigate SIM presence/ready/PIN/ICCID/IMSI/MSISDN, operator/PLMN/MCC-MNC/registration/roaming/RAT, band/EARFCN/cell/PCI/signal metrics, active APN/PDP/IP-family/cellular state, and modem firmware revision where exposed. Do not require every field to exist or implement production detection.

Inspect available firmware/web assets for actual XHR/fetch/RPC/CGI/UBus requests and response fields first. Then observe or invoke only requests evidenced as read operations, preferably those generated by status pages. Use an existing legitimate router session where practical; never store/log passwords, cookies, or tokens. Do not interact with controls or operations that change configuration, connections, services, SMS, SIM state, APN, RAT/network mode, or band locks. No guessed AT/UBus/CGI/RPC method or unknown-side-effect modem command is permitted.

For each candidate record its source/page/path, exact method/request, read-only basis, authentication requirements, masked response shape, observed fields, state-change observation, and VERIFIED / INFERRED / NOT FOUND / UNTESTED classification. If safety is unverified, do not execute it; record that limit explicitly. Units/status interpretation require evidence independently of field existence. Neutral PLMN/operator values must not be mapped to a carrier in this task.

Extend `tools/d2_discovery.py` only with explicitly allowlisted evidenced getters. Keep normal output masked/omitted, raw capture opt-in and gitignored, deadlines/output bounded, cancellation cooperative, and production startup inert. Add sanitized observed-shape fixtures and offline coverage for missing/null/unexpected types, partial/malformed responses, observed firmware differences, and sensitive-value redaction. No test may depend on hardware.

The capability report contains a separate Task 004 cellular telemetry section with source ledger T4-S01–S05 and authenticated ledger T4-A01–A07. The active `/opt/web` Vue source establishes seven exact GET requests and view bindings. Two initially unauthenticated telemetry requests returned HTTP 401; the other five were not separately tested without the session. The firmware's `localStorage.Authorization`/Authorization-header/`withCredentials` mechanism is source-verified and was reused privately inside the tab. All seven authenticated requests returned HTTP 200/body code 200/object data.

Observed Internet fields include `Status="Connected"`, `Band="1/28"`, `RSRP="-91"`, `RSRQ="-9"`, and `SINR="22"`. Nested WAN `ConnectionStatus` includes `ConnectMode="LTE"`, `ConnectStatus="Connected"`, `USIMStatus="Ready"`, `RSRP0="-91"`, `RSRP1="-96"`, and `RSSI="-82"`; the separate WAN `ConnectMethod="GSM"` label is not interpreted as a 2G fallback. SIM information reports `SIMCardState="READY"` and `PINCheckEnabled="OFF"`. ICCID/IMSI/MSISDN and other identifier/address field presence/types are verified with values masked; operator/model/version text, PCI, and PIN-retry string values are omitted. The sanitized fixture records 49 typed fields across seven successful responses.

Masking also replaces empty strings, so identifier/address validity, non-empty state, and correspondence to the inserted SIM are unknown. Raw ready labels do not independently verify a present boolean or absent/locked states. Connected is not verified EPS registration or Internet health. Band `1/28` is not interpreted as carrier aggregation. Signal units/scale/antenna meanings and status-code interpretations remain unverified. No operator-name/PLMN/MCC-MNC value was exported or mapped to a carrier. APN/PDP/registration/roaming/EARFCN were not found in this reviewed sanitized output; omitted raw fields may exist. Modem firmware revision is not established by router/software-version keys. `wirelessinfo` exported no allowlisted fields, which does not prove empty raw data or an unsupported capability. Other firmware/SIM states remain unexercised.

Task 004 also intentionally tightens the development-summary privacy boundary. Earlier component-word matching could print arbitrary quoted values that happened to resemble an allowed dotted name. Those summaries/status-name searches now report only the exact reviewed operation `sms.get.inboxdata`; a strict source helper supplies reviewed endpoint/property metadata without literal values. Two earlier development-summary expectations were updated and a privacy regression added. Production transport and all 78 original transport tests are unchanged.

The browser probe performs only the seven allowlisted same-origin GETs in the existing legitimate signed-in tab. It keeps authorization inside that origin, requests no browser-storage/configuration writes, rejects redirects, uses a 20-second total deadline and 256 KiB response limits, and supports explicit cancellation. Brave had no accessible connector or exposed remote-debugging port/pipe, so the user manually executed the probe and supplied only its sanitized report. `state_changes_requested=false` records GET-only requested operations; firmware-internal counter/log side effects were not audited. No raw capture or credential export occurred. Task 005 was unstarted at Task 004 completion.

### Deferred DITO core services — future scope only

The following earlier proposal is not the approved Task 004. It remains unassigned future work and is not authorized by telemetry discovery.

Add DITO recognition from verified device evidence and a carrier adapter with explicit unknown/unsupported states. Move the existing DITO OTP rule into that adapter over normalized messages. Shared OTP watcher services must accept a carrier-provided matcher/predicate rather than importing DITO OTP logic directly. Recover or implement the missing polling service with injected clock/fetcher, baseline/new-message handling, freshness, bounded retry, cancellation, and SIM-change reset. Port reviewed OTP/watcher tests and add missing ordering/malformed/time-zone cases. No MyDITO automation or Smart account features are needed for Phase 1.

### Task 005 — carrier-neutral device state and D2 status client

**Complete within approved Device and normalized model scope.** Preserve Device → Carrier → Services → UI. Immutable SIM, network, radio, WAN, carrier-evidence, snapshot, and closed partial-error models now live under `src/sim_manager/`. D2-specific normalization and a single `get_device_state()` snapshot API keep raw endpoint objects inside the device boundary; future UI code must not fetch seven requests independently. The SMS transport and development tools remain separate unchanged paths.

Use only Tasks 003–004 evidence. Normalize reported bands `"1/28"` to `(1, 28)` without aggregation/primary-band meaning. Parse finite signal strings into optional numeric fields with unit-neutral names and `units_verified=False`; do not assert dBm/dB, antenna meaning, or measurement validity. Map the observed `Ready`/`READY`, `LTE`, `Connected`, and `PINCheckEnabled="OFF"` labels. Both observed Ready capitalizations are accepted across the verified state paths; defensive handling of literal `Disconnected` is not a new hardware observation. Keep explicit SIM presence, PIN-required state, registration, roaming, operator, PLMN/MCC/MNC, APN/PDP/IP family, EARFCN, and modem firmware revision unknown when not verified. PCI has a verified string field but an omitted value; defensive numeric parsing is not new hardware evidence.

Store identifier/address availability rather than full ICCID/IMSI/MSISDN/IMEI/IP/DNS values. Non-empty reported text can establish availability without establishing validity; missing/null/masked/omitted placeholders remain unknown, while an explicitly empty string can establish unavailable reported content. Model repr/str and safe issue output must omit all fields, including accidentally wrong-typed constructor arguments. Optional future operator/APN fields must not leak through diagnostics; the D2 parser leaves them unset without verified values. CarrierEvidence remains empty/UNKNOWN; never map branding, model, MAC, SSID, or unobserved operator/PLMN to a carrier.

The D2 status client uses only the fixed seven evidenced GET endpoints via the injected `AuthenticatedStatusSession.read_json()` protocol and private-boundary `StatusResponse(http_status, payload)`. The session owns legitimate authentication, TLS verification, redirect rejection, response limits, and connection cleanup; production code accepts no credential/token/header parameter and stores no Authorization value. No production Python bridge to the existing Brave session exists yet. The default missing-session path returns authentication-required unknown state without network/browser access. An explicitly injected implementation must honor one shared monotonic deadline (default 20 seconds), cooperative cancellation, and the 256 KiB per-response limit; the client cannot preempt arbitrary injected code that ignores that contract. Authentication failure stops subsequent reads. Cancellation/deadline expiry discards the late response while retaining earlier successes. Normalization and endpoint failures remain isolated so available data survives with fixed-source, closed-code partial errors and UTC/source metadata.

Test the sanitized Task 004 report, band/signal/SIM/LTE mappings, missing/null/empty/malformed/unknown values, partial endpoint failures, privacy-safe repr/logging, unknown carrier evidence, cancellation/deadline behavior, response-limit contract forwarding, and no-session inertness without hardware. No raw HTTP byte-limit enforcement is implemented or independently tested by a client receiving parsed JSON; that belongs to the future session implementation. Run both full offline suites; verify unchanged legacy paths/hashes, SMS transport and original tests, no tracked secrets/captures, and diff/whitespace. Optional safe operator verification is not needed for this task; no further hardware or probe changes are planned. Record final results below only after verification. Task 005 itself authorized no GUI, carrier login/account work, or Task 006 implementation; the later approved native-shell scope is separate below.

### Deferred local storage and minimal neutral UI — future scope only

The earlier Task 005 proposal below is not the approved Task 005. Its storage/account-oriented goals remain unassigned future work. The separately approved Task 006 below adds only the native Overview/Messages/Settings visual shell; it does not authorize configuration storage or account views.

Reuse atomic settings persistence with a single canonical saved-account schema and `%LOCALAPPDATA%/SIM Manager` paths. Preserve old app-data files; any future import must be explicit, validate input, resolve deletion/selection semantics, and never carry over authentication material or an unbound global account cache. Keep detected SIM identity separate from user-entered account numbers.

Build a local shell and the smallest device/messages/status presentation needed to exercise DITO core. Reuse useful cards/formatters but remove hardcoded availability and MyDITO-specific presentation decisions. The UI routes I/O through services; device, carrier, and storage adapters own their respective I/O. Device/status errors must leave the application usable. Complete the Data/Overview/Messages/Settings experience according to roadmap Phase 3; a minimal earlier shell is only for validating the Phase 1 path.

### Task 006 — first native desktop shell

**Complete within approved visual milestone scope.** The modular native Windows application uses PySide6 Qt Widgets and the entry point `python -m sim_manager`, with only Overview, Messages, and Settings. The existing normalized `DeviceState` reaches the UI through a service/provider and presentation model; the UI does not know endpoint paths, parse router JSON, access localStorage/Authorization values, or contain carrier logic. Every prior backend test is retained. Direct neutral status presentation follows Device → Services → UI without inventing a carrier adapter; the broader Device → Carrier → Services → UI boundary is preserved.

Overview presents SIM readiness/PIN-check state, neutral network mode/status, Carrier Unknown, optional signal/band values, WAN/address availability, and a truthful router-status indicator. Missing values display Unknown or an em dash. Unit-unverified signals must not be labeled dBm/dB; reported bands do not imply aggregation. Show safe loading, authentication-required, unavailable, partial, malformed, cancelled, and unknown-error states using fixed friendly text rather than raw errors or identifiers.

Messages remains a shell: the existing raw SMS envelope lacks a normalized message model/service suitable for this GUI, so do not bypass the service boundary to wire transport directly. No SMS read/send/delete is added. Settings shows a read-only router-address placeholder, connection/status information, and app information; no editable configuration, credential fields, storage, or carrier accounts are added.

Production uses the Task 005 status client without an authenticated session and must launch/refresh gracefully with authentication-required unknown state and no router/browser access. The production Brave/router bridge remains unresolved; never open a browser automatically. Explicit `--demo` selects a bounded offline provider derived from the sanitized Task 004 fixture. Demo labeling is permanent while that provider is active, and fixture state is never presented as live. Demo mode adds no runtime dependency on development probes or legacy files.

Refresh runs outside the Qt GUI thread using one Python daemon worker, a cooperative stop Event, and a result Queue polled by a Qt main-thread timer. Block duplicate overlapping refreshes and show a simple loading state. All widget updates remain on the main thread. Closing requests cancellation, stops polling, discards late results, and uses a bounded join; shipped production/demo providers must finish cleanly. There is no QThread lifetime to manage. Arbitrary injected providers that ignore cancellation/deadlines cannot be forcibly killed; their daemon status avoids blocking process shutdown but cannot guarantee instant thread termination. Document this residual rather than claiming forced cancellation.

The optional `desktop` extra declares `PySide6-Essentials>=6.8,<7` separately from the standard-library backend. README/WORKFLOW document editable-extra installation, `python -m sim_manager` and explicit `--demo`, standard-library backend/service tests, separate offscreen GUI tests under `tests/gui/`, and JavaScript checks. Coverage includes construction, known/missing/partial snapshots, demo/authentication indicators, refresh failures/cancellation/overlap, privacy-safe display, responsive resize, and clean shutdown. The native window starts at 1120×760 with minimum 840×600; timer polling is 50 ms and the first close join waits at most one second, with repeat shutdown non-blocking. Verification results are recorded below; no Task 007 work is authorized.

### Task 006.1 — focused UI/UX polish

**Complete within approved UI-only scope.** Preserve the existing DeviceState/provider/presentation boundary, refresh worker, offline fixture, privacy rules, and backend behavior. Routine status now uses a compact row, with banners for warnings/errors. Carrier Unknown, Network, and SIM appear first; all six development signal fields remain without inferred quality/units, and the Connection section uses compact details. Small monochrome navigation icons use Qt drawing only, selected styling and permanent demo disclosure remain, Refresh appears only on Overview, Cancel remains accessible during background work on all pages, and read-only Settings groups router/application information. Messages remains an unconnected blank state.

Verify default 1120×760, smaller 840×600, and maximized native Windows layouts plus relevant offline GUI semantics. Keep all backend/service/JavaScript tests passing; compare legacy and backend hashes, review the diff/whitespace, and record the results below. No authentication, carrier/account/SMS integration, backend functionality, or Task 007 is authorized.

### Task 007 — direct D2 authentication and live status

Approved scope: authenticate directly with the local D2 using its evidenced admin protocol, then read only the seven verified status GETs into the existing `DeviceState` → services/presentation → native GUI path. The sole permitted writes are legitimate login/session creation and optional evidenced logout. Browser discovery remains development-only. No carrier integration/mapping, SMS actions, router configuration changes, persistent credentials, or Task 008 work is authorized.

Implementation sequence:

1. Inspect active firmware login/request/interceptor sources; classify protocol, response/session/expiry and TLS evidence without guessing or exporting secrets.
2. Add an isolated, bounded, cancellable HTTPS session with private in-memory authorization and narrow router certificate handling. Cover authentication, network failures, cancellation, redaction and expiry offline.
3. Compose the live service with this session; invalidate on protected authentication failure, stop that refresh cycle, preserve appropriate partial data, and expose safe fixed service outcomes.
4. Add a masked runtime sign-in dialog through the service, sharing the existing single background worker for login and refresh. Preserve independent, visibly marked demo mode.
5. Run backend/service, GUI and JavaScript suites, syntax, installation/wheel/launch, privacy, legacy hash and tracked/untracked whitespace/diff checks. Then validate on hardware with the user entering credentials only into the application. Record any unavailable validation honestly.

The foundation plan stays active because later foundation/account tasks remain deferred. Task 007 verification is recorded separately from historical results below.

### Task 008 — read-only native SMS inbox

Approved scope: reuse the existing D2 Telnet/UBus `sms.get.inboxdata` transport → defensive carrier-neutral message parser/model → in-memory message service → Messages UI. HTTP router authentication remains separate, with no authorization passed to SMS. No SMS sending/deletion/read-state mutation, carrier OTP rules/automation, account integration, persistence, router configuration writes or Task 009 work is authorized. Legacy remains read-only.

1. Inspect legacy SMS/OTP parser and synthetic transport tests to establish supported keys, envelope variants and limits; distinguish source assumptions from observed hardware.
2. Add private-repr normalized message/inbox models and bounded parser/client/service, tolerant of missing/malformed individual entries, preserving evidence-supported order/identity without inventing read/storage semantics. Add wholly synthetic demo messages and offline coverage.
3. Replace the Messages placeholder with compact sender/time/preview rows and plain-text selection detail. Add independent background Refresh/cancellation/no overlap, preservation on failure, friendly empty/error/partial states and clean shutdown.
4. Run full backend/service, GUI and JavaScript suites; review privacy, syntax, packaging/native launches, tracked/untracked whitespace/diff and legacy hashes.
5. Only after offline tests pass, perform controlled live read-only inbox validation and Refresh. Emit counts/status/schema metadata only, never SMS bodies, sender values, IDs or OTPs; do not save live screenshots/captures. Record actual results and remaining firmware assumptions.

Task 008 is complete within this scope; verification is recorded separately below. The foundation plan stays active for later deferred tasks. Task 009 remains unstarted.

### Task 009 — isolated DITO authentication/session lifecycle

Approved scope: audit legacy and current official MyDITO authentication evidence, then implement Carrier authentication → DITO adapter/session → service → compact Settings account controls. Use an isolated, off-the-record Qt WebEngine surface only after explicit Connect. The official site handles user credentials, OTP/security challenges and consent; SIM Manager observes only source-backed closed authentication events. No balance, promos, allowances, Smart, carrier auto-detection, outbound SMS, automatic OTP submission, persistent credentials/session material or Task 010.

1. Classify legacy source and current official website evidence. Legacy URL-only success guesses, persistent profile/saved numbers, arbitrary DOM overlays, automatic OTP submission and raw watcher diagnostics are not reusable. Verify exact trusted origins, current auth success/expiry signals and minimum auth-only request paths before implementing.
2. Add opaque neutral account-state models, carrier-specific likely OTP matching, a generation-guarded service and isolated browser/profile. Do not read inputs, export cookies/tokens/storage or assume session lifetime. Keep session state in memory; explicit local Disconnect destroys the entire isolated profile, with no guessed server logout.
3. Add compact DITO Account Connect/Disconnect states and an explicit Copy OTP action. Messages remains carrier-neutral; only user-loaded normalized inboxes or explicit message selections may offer a likely match. The production reader now requests 20 records through the existing validated getter count after the original three-record window omitted the candidate and a 100-record read failed normalization. Raw transport/standalone-client defaults, deadlines and byte limits remain unchanged. No background OTP polling, fill or submission.
4. Run offline backend/service, GUI and synthetic JavaScript observer tests, packaging/native launches, privacy/whitespace/diff, and legacy baseline checks.
5. After offline success, open the official flow through the production app and request only unavoidable user interaction there. Validate legitimate sign-in, strict source-backed session establishment, GUI state and safe local disconnect. Never request credentials/OTP/cookies/tokens in chat, persist captures, or expose private live contents.

Task 009 is complete within its approved authentication/session scope; controlled live sign-in, Connected and local Disconnect passed. Verification is recorded below. The foundation plan remains active for later work; Task 010 has not begun.

### Deferred MyDITO account data and persistence — future scope only

The earlier Task 006 proposal below is not the approved Task 006. It remains unassigned future account/browser work and is not authorized by the native-shell task.

Proceed with roadmap Phase 2 after the device/services path works. Reuse selected existing browser scripts and account parsers inside the DITO integration. Use an official user-authenticated browser surface isolated from local app data, with trusted-origin checks, manual fallback, and no security bypass. Investigate actual session lifetime, endpoints/DOM behavior, and challenges rather than treating legacy guesses as facts.

Implement session persistence, logout, expiration recovery, refresh, and verified account fields incrementally. First fix time/unit interpretation and partial-account success rules; add source/account binding before implementing cache storage. Normalized allowance models must support data-only and non-expiring products without requiring calls, texts, or expiry. Use browser-executed sanitized fixtures for ambiguous inputs, navigation, overlay exclusion, rejected/expired OTPs, and account switching. Preserve last known values as visibly cached/stale; never display local usage as an official carrier balance. Keep optional OTP autofill/submission out until its verification and session binding are established.

### Later tasks

Add the Smart adapter and Smart/TNT/Smart Bro recognition in Phase 4 using the same normalized contracts. Introduce outbound SMS only after verified device-command/encoding discovery and an explicit feature task. Multi-SIM profiles, local usage history, notifications, broader hardware support, and packaging polish follow the roadmap. Rebuild launch/build commands for SIM Manager with declared dependencies and verify WebView2 runtime handling when browser integration is included.

## 8. Verification record and implementation gates

### Historical audit baseline

Audit baseline on Python 3.13.15:

```powershell
# Working directory: old/D2-desktop; -B prevents bytecode writes.
python -B -m unittest discover -s tests -v
```

Result: **75 tests passed; six test modules failed to import**. Unittest reports 81 entries because each failed module contributes one error entry. Static inspection counts 215 test methods; the whole legacy suite did not execute. Import errors affect `test_account_cache`, `test_desktop_autofill`, `test_desktop_helpers`, `test_home_dashboard`, `test_login_automation`, and `test_watcher`. Causes are absent local modules `account_cache`/`watcher` and unavailable external `webview` in this environment. All 35 supplied Python files parse successfully. No dependencies were installed and no browser/router was launched.

An additional isolated `test_otp.py` run passed 6/6. Offline probes confirmed split-Telnet-negotiation loss, acceptance of malformed envelope `data`, and failure on nonstring SMS content. These are audit observations, not new checked-in tests or evidence of live-device compatibility.

For each later implementation task: run the focused tests and package/import/start checks appropriate to its scope, verify graceful error behavior, inspect the change against this plan, and update relevant docs. Use opt-in hardware checks after offline tests; record the tested D2 firmware/configuration without retaining personal data. Keep browser/account tests independent from device tests. Update `ARCHITECTURE.md` with actual boundaries and `WORKFLOW.md` with reproducible commands once established. Move this plan to `plans/completed/` only after its foundation implementation scope is fulfilled; this audit does not mark the roadmap foundation phase complete.

File-integrity verification for the original audit used before/after SHA-256 hashes and tree comparison because Git metadata was absent. Result: this plan was the only added file; all 47 pre-existing files, including all 40 legacy files and the existing project instructions/docs, remained unchanged. No bytecode artifacts were created.

### Task 001 verification

Verified on Python 3.13.15:

- `python -B -m unittest discover -s tests -v`: **30 tests passed**.
- `python -S -B -m unittest discover -s tests -v`: **30 tests passed**, with site packages disabled. Both runs use `PYTHONPATH=src` from the new repository root; they neither import nor execute legacy files.
- Package imports also succeed with site packages disabled. Project metadata declares zero runtime dependencies; building a distribution uses the declared setuptools backend, which was not installed or exercised in this task.
- Tests block real socket construction and require fake connections. Synthetic transcripts cover default/custom connection arguments, the 0.7/0.25-second read windows and 0.5-second socket timeout, Telnet refusals/escaped IAC, exact UBus quoting/CRLF, command echo and second-marker completion, fragmented payload/markers, JSON amid shell noise, nested/stringified JSON, retries/timeouts, login prompts, disconnects, malformed/error envelopes, and socket cleanup.
- At Task 001 completion, the port and legacy `router.py` had identical SHA-256 hashes (`4050F88425B155E25C8D233CF3C1AD5A019A06F4BC0EF6DF1CCDCDB16BA1A56E`); no protocol, public interface, or exception changes were introduced during that extraction. Task 002 intentionally changes the new copy after this baseline.
- All 40 legacy files retain their original paths and SHA-256 hashes. Git is initialized only inside `sim-manager/`; no Git directory was created at the workspace root and the legacy tree is outside the repository.
- Git diff review includes new files through a temporary index; the normal index remains unstaged. No commits were created. The initial repository status lists the project files as untracked.

Observed legacy behavior differs from likely future expectations in the following ways, preserved intentionally for this baseline:

- Telnet negotiation split across receives loses state and can leak option bytes into decoded output; failed negotiation replies are swallowed.
- Completion requires two occurrences of the fixed marker. A successful echo-disabled response with one marker is reported as a timeout.
- EOF before completion is reported as a response timeout; receive-side `OSError` is reported as a connection error with its cause retained.
- Success envelopes validate only code/message/data presence. `data` need not be a valid SMS payload, and extraction enumerates nested objects; a nested success envelope can override its outer response. The last successful candidate can also be selected ahead of a later error envelope.
- Raw `OSError` text and exception chaining are unchanged. Future diagnostic callers must mask or omit sensitive content rather than blindly print exceptions or their causes.

These are historical Task 001 characterization observations, not approved permanent contracts. No live-router, hardware, modem, browser, or account verification was performed. At Task 001 completion, the four requirements above were documentation only and Task 002 had not begun. The following section records the later authorized hardening. This foundation plan remains active for its outstanding tasks.

### Task 002 verification

Verified on Python 3.13.15 from `sim-manager/` with `PYTHONPATH=src`:

- `python -S -B -m unittest discover -s tests -v`: **78 tests passed** (30 retained/updated characterization tests and 48 reliability tests). Site packages were disabled. The final run took 0.411 seconds.
- Synthetic sockets, clocks, events, and controlled connection workers cover unchanged command/default behavior, echo on/off, line/UTF-8 fragmentation, Telnet state/subnegotiation, raw-wire caps, monotonic deadlines, cancellation/late-socket cleanup, disconnects, safe envelope/wrapper selection, and sanitized exception output. No live connections occurred.
- Final idle-pacing regressions cover delayed login text after short cancellation polls, cancellation across repeated polls, delayed-login rejection through the fetch path, and a successful cancellable fetch with phase-aware fake timing. Banner/wake-up reads preserve the 0.5-second idle wait within their 0.7/0.25-second phase caps.
- All six Python files parse successfully. Package imports remain inert with real socket construction and connection calls blocked.
- All 40 legacy file paths and SHA-256 hashes match the baseline; no legacy files were added, removed, or changed.
- `git diff --check` passes, including untracked files reviewed through a temporary index. The normal index remains unstaged. On branch `main`, Task 002 changes consist of seven modified files and one untracked reliability test file. No commits were created during Task 002.

Intentional updates to Task 001 expectations: fragmented negotiation retains state; completion accepts one terminated standalone marker with echo on or off; EOF/reset is classified as a disconnect; raw I/O details and exception chains are suppressed; nested response payloads cannot override valid or malformed outer envelopes. Bytes after the completion line are excluded from response processing, including trailing JSON and Telnet negotiations. The exact UBus command, default endpoint/read count, data-shape/stringified-data lenience, last-success selection, public helper nested enumeration, and best-effort Telnet refusal errors remain covered compatibility behavior.

Remaining Task 002 limits were documented in section 7: uninterruptible OS DNS work can leave abandoned daemon workers temporarily alive, unclosed leading-brace shell noise prevents safe response resynchronization, and router firmware/line/payload assumptions remained unverified. No live-router, hardware, modem, browser, or account verification was performed during Task 002. Task 003 began later with the read-only evidence below; this foundation plan stays active.

### Task 003 verification

Verified on Python 3.13.15 from `sim-manager/` with `PYTHONPATH=src`:

- `python -S -B -m unittest discover -s tests -v`: **139 tests passed** in 1.014 seconds, with zero failures/errors. This includes all 78 unchanged transport tests and 61 new development-probe tests. Synthetic sockets/events/clocks guard against live connections and cover fixed queries, fragmented frames, bounded deadlines/output, cancellation/cleanup, login/EOF errors, safe summaries, USB/network parsing, raw-capture confinement, and inert CLI/import behavior.
- All 18 fixed query types were manually executed against the actual router. E11 was rechecked after interface-header parsing fixes. See the capability report for the exact E01–E18 ledger; no SMS or guessed vendor/AT operations were issued and no router settings were altered by the commands.
- All 40 legacy paths and SHA-256 hashes match the Task 003 baseline. Production package files, both original transport test modules, and `pyproject.toml` also match that baseline.
- `git diff --check` passes, including the three new files reviewed through a temporary index. The normal index remains unstaged. On branch `main`, changes comprise six modified documentation/ignore files and three new files: the development probe, its tests, and the capability report. No Task 003 commit was created.
- No hardware raw captures were retained or tracked; `--capture-raw` was never used for hardware. The `/artifacts/d2-private/` ignore rule is effective. Offline capture tests use temporary synthetic data only.

Task 003 is complete within its observational scope with unknowns explicitly retained. At Task 003 completion, Task 004 had not begun. The separately approved telemetry investigation follows; this foundation plan stays active for outstanding work.

### Task 004 verification

Offline verification and scoped authenticated discovery complete:

- Python 3.13.15, `PYTHONPATH=src`, `python -S -B -m unittest discover -s tests -v`: **190 tests passed** in 0.974 seconds, without site packages, browser dependencies, or live hardware. This includes the intentional development-summary privacy expectation changes; all 78 original transport tests remain unchanged.
- `node --test tests/test_d2_browser_probe.js`: **36 tests passed** in 693.5684 ms using fake browser requests/storage/streams and built-in Node facilities, with no npm dependencies. `node --check tools/d2_browser_probe.js` also passed.
- The sanitized observed fixture `tests/fixtures/d2/authenticated-report.json` exactly preserves the user-provided report with notes: seven successful responses and 49 typed fields, with no seven-or-more-digit strings. Tests that reconstruct hidden values use explicitly synthetic data. Missing/null/unsafe values, privacy masking, bounded reads/deadlines/cancellation, and authentication staying in origin remain offline concerns.
- Actual firmware/admin source inspection identified the separate Vue UI, exact seven GET paths, response/view bindings, and authentication mechanism. HTTPS root returned 200; the two unauthenticated dashboard telemetry requests returned 401. The user-supplied authenticated Brave report returned HTTP/body code 200 and object data for all seven GETs; other endpoints' unauthenticated requirements were not isolated.
- All 40 legacy paths/hashes, production package files, original transport tests, and package metadata remain unchanged. No router-setting writes or tracked sensitive captures were introduced.
- Git remains on `main` with an unstaged normal index and no Task 004 commit. Aggregate Task 003/004 status is six modified files and twelve untracked files; Task 004 relative to its starting snapshot changes eight files and adds nine files. Diff review and `git diff --check` pass; all twelve untracked files also pass read-only `git diff --no-index --check` against `NUL`. The normal Git index was not changed.

Task 004 is complete within its observational scope. Raw labels/typed fields are established; masked identifier content, omitted operator/PCI/retry values, units, status semantics, unavailable-field conclusions, modem firmware revision, absent/locked SIM states, and firmware variations remain explicitly unverified. No production telemetry/carrier implementation or Task 005 work occurred. This plan stays active for deferred foundation work.

### Task 005 verification

Verified offline on Python 3.13.15 from `sim-manager/` with `PYTHONPATH=src`:

- `python -S -B -m unittest discover -s tests -v`: **260 tests passed**, zero failures/errors, in 1.888 seconds. All 190 prior tests, including 78 original SMS transport cases, remain unchanged; 31 parser/model and 39 client cases were added.
- `node --test tests/test_d2_browser_probe.js`: **36 tests passed** in 688.2856 ms; `node --check tools/d2_browser_probe.js` passed. The development browser tools/tests/fixtures are unchanged.
- Offline fake-session/normalization tests cover the observed sanitized shape, band/signal/Ready/LTE mappings, missing/null/empty/malformed/future fields, canonical-state and valid-field precedence, partial endpoint failures, opaque repr/logging, identifier/address availability, unknown carrier evidence, no-session no-I/O, shared deadlines/cancellation/late-response discard, authentication stops, and byte-limit contract forwarding. No raw HTTP enforcement or new hardware semantics are claimed.
- Five new files: `src/sim_manager/models.py`, `src/sim_manager/devices/d2/status_parser.py`, `src/sim_manager/devices/d2/status.py`, `tests/test_d2_status_parser.py`, and `tests/test_d2_status_client.py`. Six updated documentation files: `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/WORKFLOW.md`, `docs/devices/D2-HARDWARE-CAPABILITIES.md`, and this plan.
- All 40 legacy file paths/SHA-256 hashes and 19 pre-existing non-document project files match the Task 005 baseline. This preserves SMS transport/original tests, all development tools/tests/fixtures, package initializers/metadata, and ignore rules. No new live-router/browser access or setting-changing operation occurred. No `artifacts/d2-private/` directory or tracked capture exists; the ignore rule is effective.
- All five new Python files parse successfully. Code/test privacy review found no real identifier or credential values; long digit test inputs are reviewed synthetic malformed-PCI vectors. Opaque repr/logging is covered. `git diff --check` passes, and each of the five untracked files passes read-only `git diff --no-index --check` against `NUL`.
- Git is on `main` with six modified documentation files and five untracked source/test files. `git rev-parse --show-toplevel` confirms `C:\PROJECTs\SIM-manager_workspace\sim-manager`. No Git initialization occurred in Task 005; the pre-existing workspace-root `.git` directory was left untouched. The normal index remains unstaged; no Task 005 commit was created. Task 004 Git counts above remain its historical record.

Task 005 is complete within its approved device-boundary scope. The production authenticated-session implementation remains unresolved and explicit; unknown units/carrier/identifier/state semantics remain unknown. GUI/storage/account features and Task 006 were not begun. This foundation plan stays active for deferred work.

### Task 006 verification

Verified within the approved desktop-shell scope:

- Python 3.13.15, `PYTHONPATH=src`, `python -S -B -m unittest discover -s tests -v`: **285 tests passed**, zero failures/errors, in 2.150 seconds. This retains all 260 prior tests and adds 25 service/presentation/demo cases without Qt or live I/O.
- PySide6/Qt 6.11.2, `QT_QPA_PLATFORM=offscreen`, `python -B -m unittest discover -s tests/gui -v`: **30 GUI tests passed**, zero failures/errors, in 5.092 seconds. Construction/rendering, missing/partial/auth/demo/error/privacy, navigation/resize, background refresh/main-thread delivery/overlap/cancellation, and worker shutdown are covered with fake/offline providers.
- `node --test tests/test_d2_browser_probe.js`: **36 tests passed** in 459.8918 ms; `node --check tools/d2_browser_probe.js` passed.
- Native Windows-platform production/demo construction, show, refresh, and close checks passed. Native screenshots were visually inspected for readable fonts and content fit at 1120×760; no `sim-manager-refresh` workers remained. Repeated shutdown is non-blocking after the first join bounded to one second. Non-cooperative arbitrary injected providers retain the documented daemon-thread limit.
- An ignored local `.venv` was created with `python -m venv --system-site-packages .venv` to reuse preinstalled Qt. `.venv/Scripts/python -m pip install -e ".[desktop]"` succeeded. Both installed `python -B -m sim_manager` and `--demo` launched native windows from the workspace parent with `PYTHONPATH` removed, then closed with exit code 0 and no stdout/stderr/orphan workers or processes. README documents normal clean-venv setup; a fresh fully isolated dependency installation was not separately exercised.
- `python -m pip wheel . --no-deps --wheel-dir dist` succeeded. The wheel contains the module entry point, UI, services, and exact sanitized demo resource; tests and legacy code are excluded. The packaged resource is byte-identical to `tests/fixtures/d2/authenticated-report.json`.
- Eighteen files were added (17 Python and one JSON): `src/sim_manager/__main__.py`, `app.py`, `devices/d2/demo.py`; `services/{__init__,device,presentation}.py`; `resources/__init__.py` and `resources/d2-demo-report.json`; `ui/{__init__,main_window,refresh,theme}.py`; `ui/pages/{__init__,overview,messages,settings}.py`; `tests/test_device_services.py`; and `tests/gui/test_desktop.py`. Six documentation files and `pyproject.toml` were modified.
- All 40 legacy paths/SHA-256 hashes and 27 pre-existing project files outside approved documentation/metadata edits remain unchanged. AST/TOML syntax, privacy review, tracked `git diff --check`, and all eighteen untracked whitespace checks passed. New files contain no seven-or-more-digit text values, and UI imports/source contain no D2/development/browser module dependencies, REST endpoint paths, or localStorage access. No private captures or staged changes exist; no credentials/identifiers, router/browser access, or setting-changing operation were introduced. `.venv/`, build/distribution outputs, and egg-info remain ignored.
- Startup without Qt (`python -S -B -m sim_manager`) gives only the friendly desktop installation instruction and expected exit code 1, without a raw traceback. `--help` works without Qt. No owned installed-CLI Python processes remained after native close checks.
- Git is on `main` with seven modified files and eighteen untracked files. The normal index remains unstaged, and no Task 006 commit was created. Historical Task 005 Git counts above describe its earlier verification point.

Task 006 is complete as the first runnable native desktop milestone. The authenticated-session bridge remains unresolved, Messages is a shell, Settings is read-only, carrier remains Unknown, and no broader account/storage/SMS feature is claimed. Task 007 remains unstarted; the foundation plan stays active for deferred work.

### Task 006.1 verification

- Python 3.13.15: **285 backend/service tests passed** in 1.334 seconds with site packages disabled; **38 GUI tests passed** in 5.945 seconds with PySide6/Qt 6.11.2 offscreen; **36 Node tests passed** in 926.7061 ms. All suites have zero failures/errors. All 30 prior GUI cases remain; only the routine success-row wording expectation changes, and eight focused polish cases cover status/banner geometry, demo clarity, page controls/cancellation, icons, hierarchy, Settings groups, and resizing/scroll bounds.
- Native Windows normal/demo layouts were captured on Overview, Messages, and Settings at default 1120×760, minimum 840×600, and maximized 1600×837 on the verification display. Screenshots were visually inspected, all 18 page/size/mode combinations had zero horizontal/vertical scroll range, and no clipping/overlap was found. Routine status is 19 pixels high versus 39 pixels for an authentication warning. No refresh workers remained after close. Scroll areas remain as a fallback for longer content or larger fonts rather than forcing a fixed content height.
- Routine live success says “Router data available” rather than claiming verified persistent router connectivity or displaying a freshness label that could become stale. Demo success says “Demo data • Router not connected”; the DEMO badge and sidebar offline-fixture disclosure remain during navigation, refresh, cancellation, and errors. Network Connected continues to describe only the normalized network field. Carrier stays Unknown.
- Dynamic status padding initially retained stale layout margins; a small status frame with explicit layout margins now separates compact text from warnings/errors. Field-name wrapping also keeps fallback/large-font labels from forcing horizontal scrolling. These fixes change presentation only; no timer/thread/provider or DeviceState architecture changes were needed.
- Task 006.1 changes five existing UI files (`main_window.py`, `theme.py`, and the three pages), adds `ui/icons.py`, updates the GUI test module, README, and this plan. No application entry point, backend, model, service, transport, fixture/resource, dependency, or development-probe file changed. No router/browser access, authentication/carrier/SMS integration, or settings edits occurred. All 40 legacy paths/SHA-256 hashes and 44 pre-task project files outside the eight approved edits are unchanged. AST syntax checks passed for all 32 Python files, tracked `git diff --check` passed, and all 19 untracked files passed whitespace checks. Source/privacy and Git diff review found no raw payload, credential, endpoint, or carrier logic introduced into the UI.
- Git remains on `main`: seven modified tracked files and nineteen untracked files, including the previous uncommitted Task 006 work. Relative to the Task 006.1 starting snapshot, eight files changed and only `ui/icons.py` is new. Nothing is staged, and no commit was created. Native screenshots remain outside the repository in the temporary directory.
- Task 007 remains unstarted. Existing authentication, unverified telemetry semantics, and injected non-cooperative-provider limits are unchanged.

### Task 007 verification

Verified 2026-10-08 (Asia/Irkutsk), Python 3.13.15 and PySide6/Qt 6.11.2:

- **368 backend/service tests** passed in 0.974 seconds; **56 GUI tests** passed in 11.130 seconds; **36 Node tests** passed in 483.2556 ms. JavaScript syntax, all 42 Python AST parses and TOML syntax passed. Synthetic coverage includes successful/rejected/malformed/missing-token login, exact username/password JSON, safe headers/token validation, session expiration and explicit reauthentication, connection/TLS failures, timeout, connect/handshake/send/read cancellation, response limits, redirects, late-result races, partial status, secret/context redaction, blank/masked dialog validation, successful worker login→snapshot, demo isolation and clean shutdown.
- Inspected active app/login/Axios bundles before implementing login. Sanitized source ledger records hashes/modules/offsets: `POST /web/v1/user/login`, JSON runtime username/password with no cryptographic transform, `code=200`/`data.Authorization`, opaque verbatim Authorization header, source-only logout and UI inactivity behavior. Username starts blank; no default was guessed. User entered credentials only in the application. Server TTL and hardware wrong-password/logout behavior remain unknown.
- Bundled public firmware certificate matches the local peer and includes IP SAN `192.168.1.1`, valid through 2030-10-26. Production uses this sole anchor only for the exact default origin, with certificate and hostname verification enabled. Direct-IP sockets avoid DNS, all redirects are rejected, and there is no insecure fallback or global certificate change.
- Actual production transport returned HTTP 401 for one unauthenticated approved getter. Then **one legitimate login and two complete seven-GET status cycles** passed: initial automatic refresh and Overview Refresh. Both yielded complete live `DeviceState`, seven successful sources and no errors. Native screenshot review confirmed LIVE, Ready/Off, LTE/Connected, bands 1/28, RSRP -87/-95, RSRQ -9, RSSI -76, SINR 23, WAN Connected/address Reported, and Carrier Unknown. Only safe presentation output was emitted; no authenticated raw capture was saved. Cookies/browser storage/custom origin or CSRF headers were unnecessary for this observed session.
- Authentication and refresh share one background worker, with no overlap. Login and snapshot have separate 20-second deadlines, cancellable nonblocking transport and 256 KiB body caps. Expired authentication invalidates and stops the cycle even when cancellation/deadline wins UI priority. Explicit sign-in is required again; credentials are not retained. Closing cancels work and discards local authorization without sending logout. The owned live-validation window closed with exit 0. Actual expiry timing was not forced on hardware; offline tests verify expiry/relogin behavior.
- Existing-environment editable installation and wheel build succeeded. The 32-entry wheel contains session/errors/dialog/services, exact public PEM and exact sanitized demo resource, excluding tools/tests/legacy. Both exact installed `python -B -m sim_manager` and `--demo` launched native windows from the workspace parent without `PYTHONPATH`/offscreen override, then closed via their owned Qt handles with exit 0, empty stdout/stderr and no owned orphans. Fresh isolated Qt dependency installation was not separately exercised.
- Task 007 creates ten files: `devices/d2/{errors,session}.py`, `resources/d2-server.pem`, `ui/authentication.py`, `tests/gui/test_authentication.py`, `tests/test_{d2_session,live_device_service,d2_auth_evidence}.py`, `tests/fixtures/d2/auth-source-evidence.json` and `tools/d2_auth_evidence.py`. It changes eight existing source files (models/status, device/presentation services, main window/refresh/theme/Settings), six guidance/docs/plan files and `pyproject.toml` certificate packaging. Earlier uncommitted Task 006/006.1 work is preserved.
- All 40 legacy paths/SHA-256 hashes and every pre-existing source/test/tool file outside the eight approved source edits remain unchanged. No credentials/session values, cookies, raw authenticated captures or sensitive identifiers were added to source/fixtures; the public PEM is not a secret. Tracked and untracked whitespace and diff review pass. Git remains on `main`, with nine modified tracked files and 29 untracked files across prior work plus Task 007; nothing is staged and no commit was created.
- No APN/network/band/SMS/reboot/reset/Wi-Fi/SIM-PIN/password/firmware/configuration request was sent. No carrier integration, mapping or Task 008 began. Unknown units, registration/roaming and carrier evidence remain explicit. Task 007 is complete within the approved scope. The foundation plan stays active for later deferred work.

### Task 008 verification

Verified 2026-10-08 (Asia/Irkutsk), Python 3.13.15 and PySide6/Qt 6.11.2:

- **429 backend/service**, **84 GUI** and **36 Node tests** passed, 549 total. Added 61 backend/service and 28 GUI cases for response shapes, missing/malformed fields, encoding/control replacement, duplicates/order, cancellation/deadlines/errors/privacy, selection, independent refresh, demo separation, composition and shared shutdown. All 50 Python AST parses, TOML and JavaScript syntax passed.
- Exactly two controlled getter calls through the unchanged local D2 Telnet/UBus transport: first native Messages navigation and its Refresh, each yielding **3 complete messages**, no issues. UI selection matched full content in memory, heartbeat confirmed responsiveness, raw/normalized record sets were unchanged, and closure cleared widgets with exit 0. No HTTP session or password prompt was required. Only counts/status/schema metadata left the process: zero application stdout/stderr bytes/log records, no live screenshot/raw capture/message fixture. No send/delete/read-state/configuration request was made; firmware-internal effects remain unknown beyond equal returned records.
- Live schema confirms JSON-string `data.ItemList`, integer `SmsId`, string sender/date/time/content and boolean `readed`. Read semantics/storage, timezone/newest-first, pagination, multipart/other encodings and other firmware remain unverified. The existing position-zero three-record limit is disclosed; read-state/storage are omitted from the neutral model. No carrier OTP/account logic or Task 009 began.
- Four new runtime files: `message_models.py`, `devices/d2/messages.py`, `services/messages.py`, `ui/messages_refresh.py`. Four new synthetic test files: `tests/test_d2_messages.py`, `tests/test_message_services.py`, `tests/gui/test_messages.py`, `tests/gui/test_app_messages.py`. Four existing runtime files changed: `app.py`, `ui/main_window.py`, `ui/pages/messages.py`, `ui/theme.py`. Updated AGENTS, README, architecture, workflow, capability report and this plan.
- Existing-environment editable install and wheel build passed. Both exact installed normal/demo module launches from the workspace parent with no PYTHONPATH/offscreen override opened native windows, closed with exit 0, empty stdout/stderr and no owned orphans. Wheel contains the new runtime modules and unchanged exact public certificate/sanitized status demo resource, excluding tests/tools/legacy. Fresh isolated Qt dependency installation was not separately exercised.
- All 40 legacy hashes and 53 pre-existing project files outside the ten approved changes match the Task 008 clean baseline, including router transport, HTTP/session/status infrastructure and existing tests/tools. Privacy and tracked/untracked whitespace/diff review pass. Git on `main`: ten modified tracked files, eight new files, nothing staged and no commit created. Task 008 is complete; the foundation plan remains active for future work.

### Task 009 verification

Offline and infrastructure verification on 2026-10-08 (Asia/Irkutsk), Python 3.13.15 and PySide6/Qt 6.11.2:

- **500 backend/service tests**, **128 GUI tests** and **57 Node tests** passed, 685 total, with zero failures. Synthetic coverage includes disconnected/successful/rejected/expired states, explicit Disconnect, reconnect, cancellation, stale callbacks, likely OTP positive/negative/ambiguity/selection/privacy, private exception suppression, token/cookie redaction, request/origin restrictions, profile isolation and clean shutdown. The backend remains standard-library-only with site packages disabled. No test performs live login or uses real credentials/messages.
- A native blank-browser construction/disposal check passed with zero stderr bytes and page-before-profile destruction. Explicit Connect alone starts the official WebEngine surface; normal startup and DEMO do not load it. Installed normal/demo commands from the workspace parent, without PYTHONPATH or offscreen override, opened native windows and closed with exit 0, zero stdout/stderr bytes and no owned orphans.
- Existing-environment editable installation and wheel build passed. All 41 packaged runtime files match source bytes; the 45-entry wheel includes the auth observer JavaScript, public D2 certificate and sanitized demo resource, declares desktop Addons, and excludes tests/tools/legacy. A separate fresh isolated Qt dependency installation was not exercised.
- The same read-only SMS getter returned 20 complete messages at the chosen count; 100 failed safe malformed-response normalization. Native initial load and Refresh both displayed 20 complete records with no issues, selection/detail consistency, responsiveness and content clearing. Returned records were unchanged. Only counts/status/schema left validation; no live SMS screenshot, raw capture, private fixture, stdout/stderr or application log record was produced. Raw transport/standalone client defaults, deadlines/cancellation/cap remain unchanged.
- Nine new runtime files: `account_models.py`, `carriers/__init__.py`, `carriers/dito/{__init__,auth_policy,browser,otp}.py`, `carriers/dito/auth_observer.js`, `services/accounts.py`, and `ui/accounts.py`. Seven new test/evidence files: `tests/test_{account_services,dito_otp,dito_auth_policy}.py`, `tests/test_dito_auth_observer.js`, `tests/gui/test_{accounts,dito_browser}.py`, and `tests/fixtures/dito/auth-source-evidence.json`.
- Existing runtime changes: `app.py`, `devices/d2/messages.py`, `services/messages.py`, `ui/main_window.py`, and `ui/pages/{messages,settings}.py`; four existing tests change (`tests/test_{d2_messages,message_services}.py`, `tests/gui/test_{app_messages,desktop}.py`). Documentation changes: AGENTS, README, architecture, workflow, DITO guide, D2 capability report and this plan. `pyproject.toml` adds the optional WebEngine dependency and observer package data.
- All 40 legacy file paths/hashes and 53 pre-existing project files outside the 18 approved changes match the clean Task 009 baseline at HEAD `b046307`. All 63 Python AST parses, TOML/JSON and four JavaScript syntax checks pass. Privacy review and tracked/untracked whitespace/diff checks pass. Git remains on `main`, with 18 modified tracked files and 16 new files; nothing staged, no commit created. No configuration/outbound SMS/account-data operation or Task 010 was implemented.
- The final controlled single-window run passed: legitimate user sign-in wholly within the official isolated page, strict `loginSuccess === true` plus exact subsequent `/pto/home`, Connected GUI and `SessionValidity.VALIDATED`, followed by the explicit local Disconnect button, Not connected, profile disposal, responsive event loop and process exit 0. The allowlist admitted 12 auth/bootstrap requests and blocked two non-auth API attempts plus 15 external requests. Application log records/private stderr bytes were zero; no credentials/codes/session values, account data, live SMS screenshots or raw captures were exported. Earlier cancellation and a separate normal app window did not provide the final automation result; they were resolved by this single-window run. Server expiry/logout/revocation and repeated live reconnect remain untested; offline tests verify lifecycle/expiry behavior without inventing a TTL.

Task 009 is complete. The foundation plan remains active for deferred work; Task 010 has not begun.

## 9. Requested outcome summary

- **Keep:** D2 Telnet/UBus inbox protocol and error vocabulary, tested OTP/parser behavior, atomic JSON persistence, pure formatting/masking utilities, selected Windows helpers and UI presentation ideas.
- **Refactor:** device SMS normalization, DITO OTP/content rules, MyDITO browser/account code, saved-account schema and cache identity, time/unit handling, controller orchestration, and carrier-specific UI coupling.
- **Remove from the new runtime:** duplicate helper/Tkinter application flows, raw sensitive debugging, remote-page application overlay/mailboxes, hardcoded router availability, global unbound account cache assumptions, and old branding/launch/build entry points. Preserve `old/` intact.
- **Build new:** minimal package/test/dependency setup, verified SIM/network/signal/device-capability queries, carrier/service contracts, missing polling/cache implementations if unrecoverable, neutral local UI, account-bound session/cache lifecycle, and later Smart support/outbound SMS.
- **Completed foundation steps:** Task 001 established the package and characterized the preserved D2 SMS transport; Task 002 completed scoped transport hardening with 78 passing offline tests. Task 003 completed observational hardware discovery, a development probe, and a capability report with 139 passing offline tests. Task 004 completed firmware/admin-UI telemetry discovery with seven sanitized authenticated GET observations, 190 passing Python tests, and 36 passing Node tests. Task 005 added normalized device state and an authentication-isolated D2 status client, with 260 passing Python tests and 36 passing Node tests. Task 006 added the runnable native PySide6 shell with 285 backend/service, 30 GUI, and 36 Node tests plus native/packaging checks; Task 007 completed direct local authentication/live status with 368 backend/service, 56 GUI and 36 Node tests. Task 008 completed the read-only live Messages inbox with 429 backend/service, 84 GUI and 36 Node tests plus controlled initial load/Refresh, privacy, native/packaging and integrity checks. Task 009 completed isolated DITO authentication/session lifecycle with 500 backend/service, 128 GUI and 57 Node tests plus controlled official sign-in, Connected and local Disconnect/profile disposal, a verified 20-record production Messages window, native/packaging/privacy/integrity checks. Account data, carrier detection, Smart and persistence remain deferred; Task 010 has not begun.
